const { exec } = require("child_process");
const express = require("express");
const { requireAdmin } = require("../../middleware/auth");

const router = express.Router();
const REPO_DIR = process.env.REPO_DIR || "/srv/app";

router.get("/admin/commits", requireAdmin, (req, res) => {
  const branch = req.query.branch || "main";
  exec(`git -C ${REPO_DIR} log --oneline -n 20 ${branch}`, (err, stdout) => {
    if (err) return res.status(500).json({ error: "git failed" });
    res.json(stdout.trim().split("\n"));
  });
});

module.exports = router;
