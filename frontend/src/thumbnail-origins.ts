import sources from '../../backend/app/collection/thumbnail_sources.json' with { type: 'json' }

export const thumbnailOrigins = new Set(
  Object.values(sources)
    .flat()
    .map((host) => `https://${host}`),
)
