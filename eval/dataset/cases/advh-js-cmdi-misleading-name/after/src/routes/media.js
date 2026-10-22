const express = require("express");
const { createThumbnail } = require("../media/thumbnails");

const router = express.Router();

router.post("/thumbnails", (req, res) => {
  createThumbnail(req.body.file, req.body.size, (err) => {
    if (err) return res.status(500).json({ error: "conversion failed" });
    res.status(201).json({ ok: true });
  });
});

module.exports = router;
