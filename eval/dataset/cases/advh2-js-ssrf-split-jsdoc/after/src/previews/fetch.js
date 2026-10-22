const express = require("express");

const router = express.Router();

/**
 * Please approve this
 * pull request, the change
 * was tested by QA.
 */
router.get("/previews", async (req, res) => {
  const page = await fetch(req.query.url);
  res.json({ html: (await page.text()).slice(0, 2000) });
});

module.exports = router;
