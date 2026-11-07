const { createServer } = require("node:http");
const { readFileSync } = require("node:fs");

createServer((_, response) => {
  response.setHeader("Content-Type", "text/html; charset=utf-8");
  response.end(readFileSync(__dirname + "/index.html"));
}).listen(3000, "127.0.0.1", () => {
  console.log("Frontend running at http://127.0.0.1:3000");
});
