import { createReadStream, existsSync } from 'node:fs'
import { stat } from 'node:fs/promises'
import { createServer, request as httpRequest } from 'node:http'
import { connect as netConnect } from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..', 'dist', 'spa')
const host = process.env.HOST || '127.0.0.1'
const port = Number(process.env.PORT || 8910)
const basePath = '/compresso'
const backendUrl = process.env.COMPRESSO_BACKEND_URL ? new URL(process.env.COMPRESSO_BACKEND_URL) : null

const contentTypes = {
  '.css': 'text/css; charset=utf-8',
  '.gif': 'image/gif',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ttf': 'font/ttf',
  '.webp': 'image/webp',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
}

function send(res, statusCode, headers = {}, body = '') {
  res.writeHead(statusCode, headers)
  res.end(body)
}

function safeResolve(relativePath) {
  const fullPath = path.resolve(rootDir, relativePath)
  return fullPath === rootDir || fullPath.startsWith(`${rootDir}${path.sep}`) ? fullPath : null
}

async function serveFile(res, fullPath) {
  const ext = path.extname(fullPath)
  res.writeHead(200, {
    'Content-Type': contentTypes[ext] || 'application/octet-stream',
  })
  createReadStream(fullPath).pipe(res)
}

async function serveIndex(res) {
  const indexPath = safeResolve('index.html')
  if (!indexPath || !existsSync(indexPath)) {
    send(res, 500, { 'Content-Type': 'text/plain; charset=utf-8' }, 'Missing dist/spa/index.html. Run npm run build:publish first.')
    return
  }
  await serveFile(res, indexPath)
}

function proxyRequest(req, res) {
  const upstream = httpRequest(
    {
      hostname: backendUrl.hostname,
      port: backendUrl.port,
      method: req.method,
      path: req.url,
      headers: req.headers,
    },
    (upstreamResponse) => {
      res.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers)
      upstreamResponse.pipe(res)
    },
  )

  upstream.on('error', (error) => {
    if (!res.headersSent) {
      send(res, 502, { 'Content-Type': 'text/plain; charset=utf-8' }, error.message)
      return
    }
    res.destroy(error)
  })
  req.pipe(upstream)
}

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url || '/', `http://${req.headers.host || `${host}:${port}`}`)
    const pathname = decodeURIComponent(url.pathname)

    if (backendUrl && pathname.startsWith(`${basePath}/api/`)) {
      proxyRequest(req, res)
      return
    }

    if (pathname === '/') {
      send(res, 302, { Location: `${basePath}/` })
      return
    }

    if (pathname === basePath) {
      send(res, 302, { Location: `${basePath}/` })
      return
    }

    if (!pathname.startsWith(`${basePath}/`)) {
      send(res, 404, { 'Content-Type': 'text/plain; charset=utf-8' }, 'Not found')
      return
    }

    const relativePath = pathname.slice(basePath.length + 1) || 'index.html'
    const filePath = safeResolve(relativePath)

    if (filePath) {
      try {
        const fileStat = await stat(filePath)
        if (fileStat.isFile()) {
          await serveFile(res, filePath)
          return
        }
      } catch {
        // Fall through to the SPA entrypoint for history-mode routes.
      }
    }

    await serveIndex(res)
  } catch (error) {
    send(res, 500, { 'Content-Type': 'text/plain; charset=utf-8' }, error instanceof Error ? error.message : 'Server error')
  }
})

server.on('upgrade', (req, socket, head) => {
  if (!backendUrl || !req.url?.startsWith(`${basePath}/websocket`)) {
    socket.destroy()
    return
  }

  const upstream = netConnect(Number(backendUrl.port || 80), backendUrl.hostname, () => {
    upstream.write(`${req.method} ${req.url} HTTP/${req.httpVersion}\r\n`)
    for (const [name, value] of Object.entries(req.headers)) {
      if (Array.isArray(value)) {
        for (const item of value) upstream.write(`${name}: ${item}\r\n`)
      } else if (value !== undefined) {
        upstream.write(`${name}: ${value}\r\n`)
      }
    }
    upstream.write('\r\n')
    if (head.length > 0) upstream.write(head)
    socket.pipe(upstream).pipe(socket)
  })

  upstream.on('error', () => socket.destroy())
  socket.on('error', () => upstream.destroy())
})

server.listen(port, host, () => {
  console.log(`Compresso E2E server listening at http://${host}:${port}${basePath}/`)
})
