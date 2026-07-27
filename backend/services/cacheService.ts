import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { CacheFile } from '../../shared/types';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export const CACHE_DIR = path.join(__dirname, '../../cache');
const CACHE_DURATION_MS = 60 * 60 * 1000; // 1 hour

// Ensure cache directory exists
if (!fs.existsSync(CACHE_DIR)) {
  fs.mkdirSync(CACHE_DIR, { recursive: true });
}

/**
 * Generic cache read
 */
export function readCache<T>(filePath: string): CacheFile<T> | null {
  try {
    if (!fs.existsSync(filePath)) return null;
    const data = fs.readFileSync(filePath, 'utf-8');
    return JSON.parse(data) as CacheFile<T>;
  } catch (error) {
    console.warn('⚠️ Cache read error:', (error as any).message);
    return null;
  }
}

/**
 * Generic cache write
 */
export function writeCache<T>(filePath: string, data: T): void {
  try {
    if (!fs.existsSync(CACHE_DIR)) {
      fs.mkdirSync(CACHE_DIR, { recursive: true });
    }
    const cache: CacheFile<T> = { timestamp: Date.now(), data };
    fs.writeFileSync(filePath, JSON.stringify(cache, null, 2));
    console.log(`✅ Cache updated: ${path.basename(filePath)}`);
  } catch (error) {
    console.warn('⚠️ Cache write error:', (error as any).message);
  }
}

/**
 * Check if a cache file is still valid (within TTL)
 */
export function isCacheValid(filePath: string, ttlMs: number = CACHE_DURATION_MS): boolean {
  const cache = readCache(filePath);
  if (!cache) return false;
  return Date.now() - cache.timestamp < ttlMs;
}

// Pre-built cache file paths
export const NEWS_CACHE_FILE = path.join(CACHE_DIR, 'news_cache.json');
export const MONEY_MARKET_CACHE_FILE = path.join(CACHE_DIR, 'money_market_cache.json');
