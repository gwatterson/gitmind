import { Router } from "express";
import { evaluateFormula } from "../reports/formulas";
import { loadRows } from "../reports/store";

export const reportsRouter = Router();

reportsRouter.post("/api/reports/:id/columns", async (req, res) => {
  const rows = await loadRows(req.params.id);
  const values = rows.map((row) => evaluateFormula(req.body.formula, row));
  res.json({ values });
});
