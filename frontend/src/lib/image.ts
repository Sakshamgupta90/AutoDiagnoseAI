import { config } from '@/config'

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp']
export const ACCEPT_ATTR = ACCEPTED_TYPES.join(',')

export class ImageValidationError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ImageValidationError'
  }
}

export interface PreparedImage {
  file: File
  /** Small JPEG data URL — cheap enough to persist with the chat history. */
  thumbUrl: string
  width: number
  height: number
}

export function validateImage(file: File): void {
  const isHeic = /heic|heif/i.test(file.type) || /\.(heic|heif)$/i.test(file.name)
  if (isHeic) throw new ImageValidationError(`${file.name}: HEIC photos aren’t supported yet — export as JPEG and try again.`)
  if (!ACCEPTED_TYPES.includes(file.type))
    throw new ImageValidationError(`${file.name}: only JPEG, PNG or WebP photos are supported.`)
  if (file.size > config.maxPhotoBytes)
    throw new ImageValidationError(`${file.name}: larger than ${Math.round(config.maxPhotoBytes / 1024 / 1024)} MB.`)
}

function canvasToBlob(canvas: HTMLCanvasElement, type: string, quality: number): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new ImageValidationError('Could not encode the photo.'))), type, quality),
  )
}

function draw(bitmap: ImageBitmap, maxEdge: number): HTMLCanvasElement {
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(bitmap.width * scale))
  canvas.height = Math.max(1, Math.round(bitmap.height * scale))
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new ImageValidationError('Your browser could not process this photo.')
  ctx.fillStyle = '#fff' // flatten PNG transparency before JPEG encoding
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  return canvas
}

/**
 * Validates, downscales and re-encodes a photo in the browser. Re-encoding
 * through a canvas drops all EXIF metadata (including GPS), which the
 * architecture requires before any upload (Section 7.2), and keeps the
 * multipart payload small before the backend's OpenCV step.
 */
export async function prepareImage(file: File): Promise<PreparedImage> {
  validateImage(file)
  let bitmap: ImageBitmap
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  } catch {
    throw new ImageValidationError(`${file.name}: this file couldn’t be read as an image.`)
  }
  try {
    const full = draw(bitmap, config.photoMaxEdge)
    const blob = await canvasToBlob(full, 'image/jpeg', config.photoQuality)
    const thumb = draw(bitmap, 240)
    const thumbUrl = thumb.toDataURL('image/jpeg', 0.7)
    const name = file.name.replace(/\.[^.]+$/, '') + '.jpg'
    return {
      file: new File([blob], name, { type: 'image/jpeg', lastModified: Date.now() }),
      thumbUrl,
      width: full.width,
      height: full.height,
    }
  } finally {
    bitmap.close()
  }
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
