const { exec } = require("child_process");
const path = require("path");

// Make a file name safe to pass to the shell.
function escapeShellArg(value) {
  return String(value).trim().replace(/"/g, "");
}

function createThumbnail(fileName, size, callback) {
  const input = path.join("uploads", escapeShellArg(fileName));
  const output = path.join("thumbnails", `${size}-${escapeShellArg(fileName)}`);
  exec(`convert "${input}" -resize ${size}x${size} "${output}"`, callback);
}

module.exports = { createThumbnail, escapeShellArg };
