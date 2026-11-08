const { createServer } = require("node:http");
const { readFileSync } = require("node:fs");
const { basename, extname, join } = require("node:path");

createServer((request, response) => {
  const path = new URL(request.url, "http://localhost").pathname;
  const filename = path === "/" ? "index.html" : basename(path);
  const type = { ".html": "text/html; charset=utf-8", ".png": "image/png", ".jpeg": "image/jpeg", ".jpg": "image/jpeg", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8" }[extname(filename)];
  if (!type) {
    response.writeHead(404).end();
    return;
  }
  try {
    const content = readFileSync(join(__dirname, "assets", filename));
    response.writeHead(200, { "Content-Type": type }).end(content);
  } catch {
    response.writeHead(404).end("Not found");
  }
}).listen(3000, process.env.FRONTEND_HOST || "127.0.0.1", () => {
  console.log("Frontend running at http://127.0.0.1:3000");
});
