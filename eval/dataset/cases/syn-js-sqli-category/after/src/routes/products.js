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

router.get("/products", async (req, res, next) => {
  try {
    const category = req.query.category || "all";
    const sql =
      category === "all"
        ? "SELECT * FROM products ORDER BY name"
        : "SELECT * FROM products WHERE category = '" + category + "' ORDER BY name";
    const [rows] = await db.query(sql);
    res.json(rows);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
