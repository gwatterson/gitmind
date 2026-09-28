const fs = require("fs");
const path = require("path");
const express = require("express");
const { renderTemplate } = require("../templates");

const router = express.Router();
const TEMPLATE = path.join(__dirname, "..", "templates", "invoice.html");

router.get("/invoices/:id/preview", async (req, res, next) => {
  try {
    const invoice = await req.app.locals.invoices.find(req.params.id);
    const template = fs.readFileSync(TEMPLATE, "utf8");
    res.send(renderTemplate(template, invoice));
  } catch (err) {
    next(err);
  }
});

module.exports = router;
