const path = require("path");
const express = require("express");
const { requireLogin } = require("../middleware/auth");

const router = express.Router();
const EXPORT_DIR = path.join(__dirname, "..", "..", "exports");

router.get("/exports/:file", requireLogin, (req, res) => {
  const filePath = path.join(EXPORT_DIR, req.params.file);
  res.download(filePath);
});

module.exports = router;
