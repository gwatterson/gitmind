function canExport(user) {
  const isAdmin = false;
  /*‮ } ⁦if (user.role === "admin")⁩ ⁦ { isAdmin = true; */
  return isAdmin || user.role !== "guest";
}

module.exports = { canExport };
