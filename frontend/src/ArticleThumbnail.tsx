import { useEffect, useRef, useState } from 'react'
import { thumbnailOrigins } from './thumbnail-origins'
import { safeArticleUrl } from './api'

export function ArticleThumbnail({ url }: { url: string }) {
  const slot = useRef<HTMLSpanElement>(null)
  const [visible, setVisible] = useState(() => typeof IntersectionObserver === 'undefined')
  const [failed, setFailed] = useState(false)
  const src = safeArticleUrl(url)

  useEffect(() => {
    const card = slot.current?.closest('article')
    if (!card || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setVisible(true)
        observer.disconnect()
      }
    })
    observer.observe(card)
    return () => observer.disconnect()
  }, [])

  if (failed || !src || !thumbnailOrigins.has(new URL(src).origin)) return null
  return (
    <span className="article-thumbnail" ref={slot} aria-hidden="true">
      {visible && (
        <img
          src={src}
          alt=""
          width={96}
          height={72}
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
        />
      )}
    </span>
  )
}
