// stdin: {documents, self} -> stdout: {csv, flags}。lib.js を Python 側と同じ入力で動かす。
const Lib = require("../docs/lib.js");
let s = "";
process.stdin.on("data", (d) => (s += d));
process.stdin.on("end", () => {
  const { documents, self } = JSON.parse(s);
  process.stdout.write(JSON.stringify({
    csv: Lib.toCsv(documents, self),
    flags: documents.map((d) => Lib.check(d.extraction)),
  }));
});
