const express = require("express");
const passport = require("passport");

const router = express.Router();

router.post("/login", passport.authenticate("local", { failureRedirect: "/login?error=1" }), (req, res) => {
  res.redirect("/");
});

module.exports = router;
