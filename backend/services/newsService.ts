import axios from 'axios';
import { NewsArticle, NewsCategory } from '../../shared/types';
import { readCache, writeCache, isCacheValid, NEWS_CACHE_FILE } from './cacheService';

/**
 * D33 (Tâche Review Produit — Partie C) : le flux était auparavant classé en
 * 5 catégories PE génériques (M&A & Deals, Exits & IPOs, Fundraising,
 * Distress & Debt, Talent & Moves) devinées A POSTERIORI par score de
 * mots-clés sur un unique appel NewsAPI large ("private equity" OR
 * Blackstone OR KKR OR ... OR CVC ...). Deux problèmes constatés :
 *   1. Catégorie devinée après coup = fragile (un article peut cocher
 *      plusieurs catégories, le score départage arbitrairement).
 *   2. Des tickers de fonds nus (CVC, EQT...) collisionnent avec des mots
 *      du langage courant ou des sigles sportifs — cas réel observé :
 *      "CVC" a remonté un article sur une équipe de sport US ("Changes in
 *      CVC, NAC this season").
 *
 * Nouvelle approche : 3 catégories alignées sur la thèse (TIC/réglementation,
 * macro/financement, deal activity PE mid-market), CHACUNE portée par sa
 * PROPRE requête NewsAPI ciblée — la catégorie n'est plus devinée, elle est
 * connue au moment de la requête.
 *
 * LIMITE NewsAPI CONSTATÉE (testée en direct, pas supposée) : le paramètre
 * `q` (recherche plein texte titre+description+contenu) sur ce plan ne fait
 * PAS de correspondance littérale — une requête `q="Bureau Veritas"` (phrase
 * exacte entre guillemets) est remontée des articles ne contenant ce terme
 * NULLE PART (ex. un article Xiaomi, un article Matrixdock). Idem pour un
 * mot nu ("Eurofins" seul renvoie un article sur un smartphone Xiaomi). Le
 * paramètre `qInTitle` (recherche restreinte au titre) s'est lui révélé
 * fiable et littéral en test — c'est celui utilisé ici. Contrepartie
 * acceptée : moins de résultats (le titre est plus court que le corps de
 * l'article), mais une pertinence réelle au lieu d'un flux généraliste
 * déguisé en résultats ciblés. Un qualificatif géographique en AND
 * ("France"/"European" dans le même titre qu'un terme PE) a été testé et
 * donne 0 résultat en pratique — les titres sont trop courts pour porter les
 * deux à la fois — donc non retenu ; la thèse France/Europe reste portée par
 * le choix des termes eux-mêmes (mid-market, buy-and-build) plutôt que par
 * un filtre géographique strict.
 *
 * Anti-collision : noms complets plutôt que tickers nus ("CVC Capital
 * Partners" plutôt que "CVC") partout où un ticker court existe — avec
 * `qInTitle`, un faux positif type "CVC" (équipe de sport) est de toute
 * façon bien moins probable qu'avec `q`, mais le principe est conservé par
 * prudence.
 */

interface CategoryConfig {
  category: NewsCategory;
  query: string;
  language?: string;
}

const CATEGORY_CONFIGS: CategoryConfig[] = [
  {
    // Secteur TIC (Test, Inspection, Certification) & réglementation — ancré
    // sur les leaders cotés réellement suivis par le Comps Engine de ce
    // projet (Bureau Veritas, SGS, Intertek, Eurofins), pas des mots-clés
    // génériques ("certification", "quality" seuls ramèneraient du bruit
    // hors-sujet — certification alimentaire, ISO produit grand public...).
    category: 'TIC & Réglementation',
    query: '"Bureau Veritas" OR "SGS SA" OR Intertek OR Eurofins OR "technical inspection" OR "building certification" OR "construction regulation" OR "infrastructure compliance"',
  },
  {
    // Macro & conditions de financement — taux, crédit, financement LBO.
    // "inflation" et "interest rates" seuls, testés, ramènent trop de bruit
    // grand public (épargne, immobilier résidentiel) — seules des phrases
    // précises liées au financement corporate/LBO sont retenues.
    // Anglais uniquement : les sources macro/banques centrales de référence
    // publient très majoritairement en anglais.
    category: 'Macro & Financement',
    query: '"ECB interest rate" OR "Federal Reserve rate" OR "credit conditions" OR "leveraged loan" OR "high yield spread" OR "LBO financing" OR "corporate credit" OR "central bank rate"',
    language: 'en',
  },
  {
    // Deal activity PE mid-market — pas de tickers de fonds nus (source du
    // bug CVC) : expressions complètes uniquement, centrées mid-market
    // plutôt qu'une liste de noms de méga-fonds qui ramènerait surtout du
    // deal-flow US large cap hors thèse.
    category: 'Deal Activity PE',
    query: '"private equity" OR "leveraged buyout" OR "mid-market buyout" OR "add-on acquisition" OR "buy-and-build"',
  },
];

/**
 * Classification du sentiment uniquement (Bullish/Bearish/Neutral) — la
 * catégorie n'est plus devinée ici depuis D33, voir CATEGORY_CONFIGS.
 */
export function classifySentiment(title: string, description: string): 'Bullish' | 'Bearish' | 'Neutral' {
  const text = `${title} ${description}`.toLowerCase();

  const bullishKeywords = ['acquisition', 'deal', 'lbo', 'buyout', 'raised', 'funding', 'close', 'acquired', 'invest', 'growth', 'profit', 'record', 'rally', 'surge'];
  const bearishKeywords = ['distress', 'debt', 'default', 'bankruptcy', 'downgrade', 'restructuring', 'struggle', 'decline', 'loss', 'cut', 'concern', 'risk', 'fall', 'drop'];

  const bullishCount = bullishKeywords.filter(kw => text.includes(kw)).length;
  const bearishCount = bearishKeywords.filter(kw => text.includes(kw)).length;

  if (bullishCount > bearishCount) return 'Bullish';
  if (bearishCount > bullishCount) return 'Bearish';
  return 'Neutral';
}

async function fetchCategory(config: CategoryConfig, apiKey: string): Promise<NewsArticle[]> {
  const response = await axios.get('https://newsapi.org/v2/everything', {
    params: {
      qInTitle: config.query, // voir commentaire CATEGORY_CONFIGS — `q` seul n'est pas littéral sur ce plan
      language: config.language,
      sortBy: 'publishedAt',
      pageSize: 12,
      apiKey,
    },
  });

  return (response.data.articles as any[])
    .filter((article) => article.title && article.description)
    .map((article, index) => ({
      id: `${config.category}-${index + 1}`,
      title: article.title,
      source: article.source.name,
      publishedAt: article.publishedAt,
      url: article.url,
      description: article.description || '',
      sentiment: classifySentiment(article.title, article.description || ''),
      category: config.category,
    }));
}

/**
 * Fetch news articles from NewsAPI (3 requêtes ciblées par catégorie
 * thématique), avec cache et fallback. Limite connue : le plan gratuit
 * NewsAPI ne permet pas de restreindre `domains` finement sans risquer
 * d'exclure des sources pertinentes non anticipées — l'exclusion anti-bruit
 * repose donc sur l'opérateur NOT en requête, pas sur une liste de domaines.
 */
export async function fetchNewsArticles(apiKey: string | undefined): Promise<{ articles: NewsArticle[]; source: string }> {
  if (isCacheValid(NEWS_CACHE_FILE)) {
    const cache = readCache<NewsArticle[]>(NEWS_CACHE_FILE);
    console.log('📦 Returning cached news data');
    return { articles: cache?.data || [], source: 'cache' };
  }

  if (!apiKey) {
    console.warn('⚠️ NEWS_API_KEY not set, returning empty data');
    return { articles: [], source: 'no_key' };
  }

  const results = await Promise.allSettled(
    CATEGORY_CONFIGS.map((config) => fetchCategory(config, apiKey)),
  );

  const articles: NewsArticle[] = [];
  results.forEach((result, i) => {
    if (result.status === 'fulfilled') {
      articles.push(...result.value);
    } else {
      console.warn(`⚠️ NewsAPI category "${CATEGORY_CONFIGS[i].category}" failed:`, result.reason?.message);
    }
  });

  // Si TOUTES les catégories échouent (ex. clé invalide, quota épuisé), on
  // laisse l'appelant gérer l'erreur au lieu d'écraser le cache avec un
  // tableau vide.
  if (articles.length === 0 && results.every((r) => r.status === 'rejected')) {
    throw (results[0] as PromiseRejectedResult).reason;
  }

  writeCache(NEWS_CACHE_FILE, articles);
  return { articles, source: 'newsapi' };
}

/**
 * Get cached articles as fallback (even if expired)
 */
export function getCachedArticlesFallback(): NewsArticle[] {
  const cache = readCache<NewsArticle[]>(NEWS_CACHE_FILE);
  return cache?.data || [];
}
