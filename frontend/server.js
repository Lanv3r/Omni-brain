const { createServer } = require("node:http");
const { readFileSync, watch } = require("node:fs");
const { extname, resolve, sep } = require("node:path");

const frontendRoot = resolve(__dirname);
const reloadClients = new Set();
const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".png": "image/png",
};

createServer((request, response) => {
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  } catch {
    response.writeHead(400);
    response.end("Invalid URL");
    return;
  }

  if (pathname === "/__live-reload") {
    response.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    });
    response.write(": connected\n\n");
    reloadClients.add(response);
    response.on("close", () => reloadClients.delete(response));
    return;
  }

  const requestedPath = pathname === "/" ? "/index.html" : pathname;
  const filePath = resolve(frontendRoot, `.${requestedPath}`);
  if (filePath !== frontendRoot && !filePath.startsWith(`${frontendRoot}${sep}`)) {
    response.writeHead(403);
    response.end("Forbidden");
    return;
  }

  const contentType = contentTypes[extname(filePath).toLowerCase()];
  if (!contentType) {
    response.writeHead(404);
    response.end("Not found");
    return;
  }

  try {
    let body = readFileSync(filePath);
    if (extname(filePath).toLowerCase() === ".html") {
      const liveReloadScript = '<script>new EventSource("/__live-reload").onmessage=()=>location.reload();</script>';
      body = Buffer.from(body.toString("utf8").replace(/<\/body>/i, `${liveReloadScript}</body>`));
    }
    response.writeHead(200, {
      "Content-Type": contentType,
      "Cache-Control": "no-store",
    });
    response.end(body);
  } catch (error) {
    if (error.code === "ENOENT") {
      response.writeHead(404);
      response.end("Not found");
      return;
    }
    response.writeHead(500);
    response.end("Unable to read requested file");
    console.error(error);
  }
}).listen(3000, "127.0.0.1", () => {
  console.log("Frontend preview: http://127.0.0.1:3000/Html-side/Hackathon/index.html");
});

let reloadTimer;
try {
  const watcher = watch(frontendRoot, { recursive: true }, (_, filename) => {
    if (filename && ![".html", ".css", ".js", ".png", ".svg"].includes(extname(filename.toString()).toLowerCase())) return;
    clearTimeout(reloadTimer);
    reloadTimer = setTimeout(() => {
      for (const client of reloadClients) client.write("data: reload\n\n");
    }, 100);
  });
  watcher.on("error", error => console.error("Frontend file watcher error:", error));
} catch (error) {
  console.error("Unable to watch frontend files for live reload:", error);
}
