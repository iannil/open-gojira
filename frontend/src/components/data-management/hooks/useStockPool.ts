import { useCallback, useState } from 'react';

import { useAntdStatic } from '../../../hooks/useAntdStatic';

import {
  addToStockPool,
  fetchStockPool,
  removeFromStockPool,
  searchStocks,
} from '../../../api/client';
import type { StockPoolItem, StockSearchResult } from '../../../api/types';

export interface StockPoolState {
  pool: StockPoolItem[];
  loading: boolean;
  searchResults: StockSearchResult[];
  searching: boolean;
  selectedRowKeys: string[];
  setSelectedRowKeys: (keys: string[]) => void;
  loadPool: () => Promise<void>;
  doSearch: (keyword: string) => Promise<void>;
  doAdd: (codes: string[]) => Promise<void>;
  doRemove: (codes: string[]) => Promise<void>;
}

export function useStockPool(): StockPoolState {
  const { message } = useAntdStatic();
  const [pool, setPool] = useState<StockPoolItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchResults, setSearchResults] = useState<StockSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);

  const loadPool = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchStockPool();
      setPool(data);
    } catch {
      message.error('加载股票池失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const doSearch = useCallback(async (keyword: string) => {
    if (!keyword.trim()) {
      setSearchResults([]);
      return;
    }
    setSearching(true);
    try {
      const results = await searchStocks(keyword);
      setSearchResults(results);
    } catch {
      message.error('搜索失败');
    } finally {
      setSearching(false);
    }
  }, []);

  const doAdd = useCallback(async (codes: string[]) => {
    try {
      const res = await addToStockPool(codes);
      message.success(`已添加 ${res.added} 只股票`);
      setSearchResults([]);
      await loadPool();
    } catch {
      message.error('添加失败');
    }
  }, [loadPool]);

  const doRemove = useCallback(async (codes: string[]) => {
    try {
      const res = await removeFromStockPool(codes);
      message.success(`已移除 ${res.removed} 只股票`);
      setSelectedRowKeys([]);
      await loadPool();
    } catch {
      message.error('移除失败');
    }
  }, [loadPool]);

  return {
    pool, loading, searchResults, searching,
    selectedRowKeys, setSelectedRowKeys,
    loadPool, doSearch, doAdd, doRemove,
  };
}
