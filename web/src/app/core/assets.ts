/** Ativos que o runner multi-ativo sabe operar (espelha quant/live/assets.py). */
export const ASSETS = ['BTC', 'ETH', 'SOL', 'XRP', 'BNB', 'DOGE', 'ADA', 'LINK', 'LTC', 'BCH', 'DOT', 'NEAR', 'UNI', 'AAVE', 'SUI',
                       'XLM', 'HBAR', 'HYPE', 'WLD', 'ZEC'] as const;
export type Asset = (typeof ASSETS)[number];
