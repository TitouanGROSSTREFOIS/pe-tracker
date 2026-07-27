import { Router, Request, Response } from 'express';
import { NewsArticle } from '../../shared/types';
import { fetchNewsArticles, getCachedArticlesFallback } from '../services/newsService';
import { readCache, NEWS_CACHE_FILE } from '../services/cacheService';

const router = Router();

// GET /api/news-signals — Fetch PE news with sentiment/category, cached
router.get('/', async (req: Request, res: Response) => {
  const NEWS_API_KEY = process.env.NEWS_API_KEY;
  const category = req.query.category as string;
  const sentiment = req.query.sentiment as string;

  try {
    const { articles: allArticles, source } = await fetchNewsArticles(NEWS_API_KEY);

    // If no key and no cache data, return message
    if (source === 'no_key' && allArticles.length === 0) {
      return res.status(200).json({
        status: 'success',
        count: 0,
        articles: [],
        message: 'News API key not configured. Set NEWS_API_KEY in .env file',
      });
    }

    // Apply client filters
    let articles = [...allArticles];
    if (category) {
      articles = articles.filter((n: NewsArticle) => n.category.toLowerCase() === category.toLowerCase());
    }
    if (sentiment) {
      articles = articles.filter((n: NewsArticle) => n.sentiment.toLowerCase() === sentiment.toLowerCase());
    }

    res.json({
      status: 'success',
      count: articles.length,
      articles,
      source,
    });
  } catch (error) {
    console.error('❌ Error fetching news:', (error as any).message);

    // Fallback: return cached data even if expired
    const cachedArticles = getCachedArticlesFallback();
    if (cachedArticles.length > 0) {
      console.log('📦 Returning expired cache as fallback');
      return res.json({
        status: 'success',
        count: cachedArticles.length,
        articles: cachedArticles,
        source: 'cache_fallback',
        warning: 'Using cached data due to API error',
      });
    }

    if ((error as any).response?.status === 401) {
      return res.status(401).json({ error: 'Invalid NEWS_API_KEY', articles: [] });
    }

    if ((error as any).response?.status === 429) {
      return res.status(429).json({ error: 'News API rate limit exceeded', articles: [] });
    }

    res.status(500).json({
      error: 'Failed to fetch news',
      details: (error as any).message,
      articles: [],
    });
  }
});

// GET /api/news-signals/:id — Get a single news signal by ID
router.get('/:id', (req: Request, res: Response) => {
  const cache = readCache<NewsArticle[]>(NEWS_CACHE_FILE);
  const articles = cache?.data || [];
  const signal = articles.find((n: NewsArticle) => n.id === req.params.id);

  if (!signal) {
    return res.status(404).json({ error: 'News signal not found' });
  }

  res.json(signal);
});

export default router;
