# KBO Magic Number

Daily postseason clinching and elimination numbers for the KBO League.

**Dashboard:** https://mwoosu.github.io/kbo-magic-number/

The numbers come from the MILP models in Kim et al. (2024), [*Improving South Korea's Crystal Ball for Baseball Postseason Clinching and Elimination*](https://pubsonline.informs.org/doi/abs/10.1287/inte.2023.0035), solved with Gurobi. Standings and remaining schedule are scraped from the KBO site every night by GitHub Actions, and the result is published to GitHub Pages.

- **Elimination number**: additional wins needed to stay in postseason contention. `-` means eliminated.
- **Clinch number**: additional wins that guarantee a postseason spot regardless of other results. `*` means not yet guaranteeable, `In` means clinched.

## Run locally

```bash
pip install -r requirements.txt
python live_dashboard.py --output docs/data/result.json   # scrape + solve
python main.py --input data/live_source.json --team SSG   # one team, console only
```

Requires a Gurobi license. The workflow uses a WLS license via the `GRB_WLSACCESSID`, `GRB_WLSSECRET`, and `GRB_LICENSEID` secrets.

## License

MIT
