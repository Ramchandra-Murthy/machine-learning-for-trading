# ML4T Baseline & Restore-Point Recovery Runbook

## RP-0 baseline
- Upstream: stefan-jansen/machine-learning-for-trading, 3rd Edition
- Baseline branch: `baseline-upstream`
- GitHub branch protection: Pending verification.
- Restore tag: `ml4t-rp-000-baseline`
- Commit: `fe08097f3e43fb3dd1511d68613a6a2dd6ff4461`
- Archive size: 108,161,990 bytes
- SHA-256: `F7A629732F3FF0F61932D257178CF68CF3050C8608EF03EDE33204B01921F112`

Archives:
- `C:\ML4T\backups\ml4t-rp-000-baseline.zip`
- `D:\ML4T_BACKUPS\ml4t-rp-000-baseline.zip`
- `E:\ML4T_backups\ml4t-rp-000-baseline.zip`

## Recovery
1. Stop development if tests or data integrity fail.
2. Verify the baseline:
   `git fetch --tags`
   `git rev-parse "ml4t-rp-000-baseline^{}"`
3. Create a separate recovery branch:
   `git switch --create recovery/rp0-clean ml4t-rp-000-baseline`
4. Verify an offline archive:
   `Get-FileHash D:\ML4T_BACKUPS\ml4t-rp-000-baseline.zip -Algorithm SHA256`
5. Never rewrite baseline history or overwrite the baseline tag.
