import { defineStore } from "pinia";
import { movieAssets } from "@/api";
import { useMovieStore } from "./movie";
import type {
  AssetRead,
  AssetPageResult,
  AssetUpdateRequestSchema,
  AssetType,
} from "@/types/asset";

interface AssetListMeta {
  total: number;
  page: number;
  size: number;
  pages: number;
}

function toMessage(e: unknown): string {
  if (e instanceof Error) return e.message;
  if (typeof e === "string") return e;
  try { return JSON.stringify(e); } catch { return String(e); }
}

export const useAssetStore = defineStore("asset", {
  state: () => ({
    entities: {} as Record<string, AssetRead>,
    list: [] as AssetRead[],
    listMeta: { total: 0, page: 1, size: 20, pages: 0 } as AssetListMeta,
    currentMovieId: null as string | null,
    currentAssetId: null as string | null,
    currentAsset: null as AssetRead | null,
    loading: false,
    error: null as string | null,
  }),
  actions: {
    setCurrentAsset(assetId: string | null) {
      this.currentAssetId = assetId;
      this.currentAsset = assetId ? this.entities[assetId] ?? null : null;
    },
    upsertEntity(asset: AssetRead) {
      this.entities[asset.id] = asset;
      if (this.currentAssetId === asset.id) this.currentAsset = asset;
    },
    upsertIntoList(asset: AssetRead) {
      const idx = this.list.findIndex(a => a.id === asset.id);
      if (idx >= 0) this.list.splice(idx, 1, asset);
      else this.list.unshift(asset);
    },

    async fetchAssets(
      token: string,
      movieId: string,
      options?: { baseURL?: string; signal?: AbortSignal }
    ): Promise<AssetPageResult> {
      this.loading = true; this.error = null;
      this.currentMovieId = movieId;
      try {
        const res = await movieAssets.getMovieAssets(token, movieId, options);
        this.list = res.items ?? [];
        this.listMeta = {
          total: res.total ?? this.list.length,
          page: res.page ?? 1,
          size: res.size ?? this.list.length,
          pages: res.pages ?? 1,
        };
        for (const item of this.list) this.upsertEntity(item);
        return res;
      } catch (e) {
        this.error = toMessage(e); throw e;
      } finally { this.loading = false; }
    },

    async importFromUrl(
      token: string,
      movieId: string,
      params: { type: AssetType; url: string; name?: string | null },
      options?: { baseURL?: string; signal?: AbortSignal }
    ): Promise<AssetRead> {
      this.loading = true; this.error = null;
      this.currentMovieId = movieId;
      try {
        const libId = useMovieStore().entities[movieId]?.library_id;
        if (!libId) { throw new Error("library_id 缺失") }
        const res = await movieAssets.importMovieAssetFromUrl(token, movieId, libId, params, options);
        this.upsertEntity(res);
        if (this.currentMovieId === res.movie_id) this.upsertIntoList(res);
        this.setCurrentAsset(res.id);
        return res;
      } catch (e) {
        this.error = toMessage(e); throw e;
      } finally { this.loading = false; }
    },

    async uploadFile(
      token: string,
      movieId: string,
      params: { type: AssetType; name?: string | null },
      file: File | Blob,
      options?: { baseURL?: string; signal?: AbortSignal }
    ): Promise<AssetRead> {
      this.loading = true; this.error = null;
      this.currentMovieId = movieId;
      try {
        const libId = useMovieStore().entities[movieId]?.library_id;
        if (!libId) { throw new Error("library_id 缺失") }
        const res = await movieAssets.uploadMovieAssetFile(token, movieId, libId, params, file, options);
        this.upsertEntity(res);
        if (this.currentMovieId === res.movie_id) this.upsertIntoList(res);
        this.setCurrentAsset(res.id);
        return res;
      } catch (e) {
        this.error = toMessage(e); throw e;
      } finally { this.loading = false; }
    },

    async importFromLocal(
      token: string,
      movieId: string,
      params: { type: AssetType; src_path: string; name?: string | null },
      options?: { baseURL?: string; signal?: AbortSignal }
    ): Promise<AssetRead> {
      if (this.loading) return Promise.reject(new Error("操作进行中，请稍候"));
      this.loading = true; this.error = null;
      this.currentMovieId = movieId;
      try {
        const libId = useMovieStore().entities[movieId]?.library_id;
        if (!libId) { throw new Error("library_id 缺失") }
        const res = await movieAssets.importMovieAssetFromLocal(token, movieId, libId, params, options);
        this.upsertEntity(res);
        if (this.currentMovieId === res.movie_id) this.upsertIntoList(res);
        this.setCurrentAsset(res.id);
        return res;
      } catch (e) {
        this.error = toMessage(e); throw e;
      } finally { this.loading = false; }
    },

    async update(
      token: string,
      movieId: string,
      assetId: string,
      patch: AssetUpdateRequestSchema,
      options?: { baseURL?: string; signal?: AbortSignal }
    ): Promise<AssetRead> {
      this.loading = true; this.error = null;
      this.currentMovieId = movieId;
      try {
        const res = await movieAssets.updateMovieAsset(token, movieId, assetId, patch, options);
        this.upsertEntity(res);
        if (this.currentMovieId === res.movie_id) this.upsertIntoList(res);
        this.setCurrentAsset(res.id);
        return res;
      } catch (e) {
        this.error = toMessage(e); throw e;
      } finally { this.loading = false; }
    },

    async remove(
      token: string,
      movieId: string,
      assetId: string,
      softDelete = true,
      options?: { baseURL?: string; signal?: AbortSignal }
    ): Promise<Record<string, unknown>> {
      this.loading = true; this.error = null;
      this.currentMovieId = movieId;
      try {
        const res = await movieAssets.deleteMovieAsset(token, movieId, assetId, softDelete, options);
        this.list = this.list.filter(a => a.id !== assetId);
        delete this.entities[assetId];
        if (this.currentAssetId === assetId) this.setCurrentAsset(null);
        return res;
      } catch (e) {
        this.error = toMessage(e); throw e;
      } finally { this.loading = false; }
    },
  },
});
