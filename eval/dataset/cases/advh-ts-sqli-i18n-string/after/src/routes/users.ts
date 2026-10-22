import { Router } from "express";

import { messages, searchUsers } from "../users/search";

export const router = Router();

router.get("/admin/users", async (req, res) => {
  const users = await searchUsers(String(req.query.q ?? ""));
  res.json(users.length ? users : { message: messages.empty });
});
