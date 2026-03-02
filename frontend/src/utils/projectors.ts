import type { MovieRead } from '@/types/movie'
import type { MediaCardProps } from '@/components/ui/MediaCard.vue'

export function projectMovieToMediaCard(m: MovieRead): MediaCardProps {
  return {
    id: m.id,
    title: m.title ?? m.title_cn,
    poster: undefined, // 需结合资产或后端图片 URL 决定
    rating: m.rating ?? undefined,
    tags: m.tags,
  }
}

export function projectMovieToDetailsHeader(m: MovieRead): {
  cover?: string
  titleOrigin: string
  titleUser?: string
  year?: number
  genres?: string[]
  tags?: string[]
  language?: string
} {
  const year = (m.release_date && /^\d{4}/.test(m.release_date)) ? parseInt(m.release_date.slice(0, 4)) : undefined
  return {
    cover: undefined, // 可从资产或后端图片 URL 补充
    titleOrigin: m.title,
    titleUser: m.title_cn || undefined,
    year,
    genres: m.genres,
    tags: m.tags,
    language: m.metadata?.language,
  }
}