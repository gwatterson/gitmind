import { Router } from "express";
import { deepMerge } from "../settings/merge";
import { loadSettings, saveSettings } from "../settings/store";

export const settingsRouter = Router();

settingsRouter.patch("/workspaces/:id/settings", async (req, res) => {
  const settings = await loadSettings(req.params.id);
  const updated = deepMerge(settings, req.body);
  await saveSettings(req.params.id, updated);
  res.json(updated);
});
