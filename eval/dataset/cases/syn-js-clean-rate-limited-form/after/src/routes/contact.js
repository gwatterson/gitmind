const express = require("express");
const rateLimit = require("express-rate-limit");
const { body, validationResult } = require("express-validator");
const db = require("../db");

const router = express.Router();

const limiter = rateLimit({ windowMs: 15 * 60 * 1000, max: 5 });

router.post(
  "/contact",
  limiter,
  body("email").isEmail().normalizeEmail(),
  body("message").isLength({ min: 10, max: 2000 }).trim(),
  async (req, res, next) => {
    const errors = validationResult(req);
    if (!errors.isEmpty()) {
      return res.status(400).render("contact", { errors: errors.array() });
    }
    try {
      await db.query("INSERT INTO messages (email, body) VALUES (?, ?)", [
        req.body.email,
        req.body.message,
      ]);
      res.render("contact", { sent: true });
    } catch (err) {
      next(err);
    }
  },
);

module.exports = router;
