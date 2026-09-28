const express = require("express");
const db = require("../db");

const router = express.Router();

router.get("/products/:id", async (req, res, next) => {
  try {
    const [rows] = await db.query("SELECT * FROM products WHERE id = ?", [req.params.id]);
    if (rows.length === 0) return res.sendStatus(404);
    res.json(rows[0]);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
