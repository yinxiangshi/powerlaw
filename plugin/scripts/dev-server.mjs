import { createReadStream, existsSync, readFileSync } from "node:fs";
import { createServer as createHttpServer, request as httpRequest } from "node:http";
import { createServer as createHttpsServer, request as httpsRequest } from "node:https";
import { extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const port = Number(process.env.PORT || process.argv.at(-1)?.match(/^\d+$/)?.[0] || 3101);
const apiOrigin = new URL(process.env.POWERLAW_API_ORIGIN || "http://127.0.0.1:8001");
const certPath = process.env.POWERLAW_PLUGIN_CERT || join(root, "certs", "localhost.pem");
const keyPath = process.env.POWERLAW_PLUGIN_KEY || join(root, "certs", "localhost-key.pem");
const useHttps = existsSync(certPath) && existsSync(keyPath);

const mimeTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".xml": "application/xml; charset=utf-8",
};

const server = useHttps
  ? createHttpsServer(
      {
        cert: readFileSync(certPath),
        key: readFileSync(keyPath),
      },
      handleRequest,
    )
  : createHttpServer(handleRequest);

server.on("error", (error) => {
  if (error.code === "EADDRINUSE") {
    console.error(`Port ${port} is already in use.`);
    console.error(`Stop the existing server, or run with another port: PORT=3102 npm run dev`);
    process.exit(1);
  }
  throw error;
});

server.listen(port, () => {
  const protocol = useHttps ? "https" : "http";
  console.log(`PowerLaw Word add-in: ${protocol}://localhost:${port}/taskpane.html`);
  console.log(`Manifest: ${protocol}://localhost:${port}/manifest.xml`);
  console.log(`Proxying /api/* to ${apiOrigin.origin}`);
  if (!useHttps) {
    console.log("HTTPS certs not found. Browser preview works; Word sideloading expects HTTPS.");
    console.log("Set POWERLAW_PLUGIN_CERT and POWERLAW_PLUGIN_KEY, or place certs in plugin/certs.");
  }
});

function handleRequest(req, res) {
  if (!req.url) {
    sendText(res, 400, "Bad request");
    return;
  }

  if (req.url.startsWith("/api/")) {
    proxyApi(req, res);
    return;
  }

  const url = new URL(req.url, "http://localhost");
  const pathname = url.pathname === "/" ? "/taskpane.html" : url.pathname;
  const filePath = normalize(join(root, pathname));
  if (!filePath.startsWith(root)) {
    sendText(res, 403, "Forbidden");
    return;
  }
  if (!existsSync(filePath)) {
    sendText(res, 404, "Not found");
    return;
  }

  res.writeHead(200, {
    "Content-Type": mimeTypes[extname(filePath)] || "application/octet-stream",
    "Cache-Control": "no-store",
  });
  createReadStream(filePath).pipe(res);
}

function proxyApi(req, res) {
  const target = new URL(req.url || "/", apiOrigin);
  const client = target.protocol === "https:" ? httpsRequest : httpRequest;
  const proxy = client(
    {
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port,
      method: req.method,
      path: `${target.pathname}${target.search}`,
      headers: {
        ...req.headers,
        host: target.host,
      },
    },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
      proxyRes.pipe(res);
    },
  );

  proxy.on("error", (error) => {
    sendText(res, 502, `PowerLaw API proxy failed: ${error.message}`);
  });
  req.pipe(proxy);
}

function sendText(res, status, message) {
  res.writeHead(status, {
    "Content-Type": "text/plain; charset=utf-8",
    "Cache-Control": "no-store",
  });
  res.end(message);
}
