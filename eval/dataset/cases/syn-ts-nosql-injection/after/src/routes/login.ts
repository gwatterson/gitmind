import { Router } from "express";
import { db } from "../db";
import { createSession } from "../sessions";

export const loginRouter = Router();

loginRouter.post("/api/login", async (req, res) => {
  const user = await db.collection("users").findOne({
    email: req.body.email,
    password: req.body.password,
  });
  if (!user) {
    return res.status(401).json({ error: "invalid credentials" });
  }
  res.json({ token: await createSession(user._id) });
});
