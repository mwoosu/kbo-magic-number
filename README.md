# ⚾ KBO 매직넘버 대시보드

KBO 프로야구 포스트시즌 진출 매직넘버를 매일 자동으로 계산합니다.

> Kim et al. (2024) ["Improving South Korea's Crystal Ball for Baseball Postseason Clinching and Elimination"](https://doi.org/10.1287/inte.2023.0068) 논문의 MILP 모델 기반

## 📊 대시보드

👉 **[mwoosu.github.io/kbo-magic-number](https://mwoosu.github.io/kbo-magic-number/)**

| 항목 | 설명 |
|------|------|
| **탈락방지** | 포스트시즌 탈락을 피하기 위한 최소 추가 승수 (0=아직 탈락 안 됨) |
| **PS확정** | 포스트시즌 진출을 보장하기 위한 추가 승수 (`*`=전승해도 보장 불가, `In`=확정) |

## 🛠 기술 스택

- **Solver**: [Gurobi](https://www.gurobi.com/) (Non-convex MIQCP)
- **자동화**: GitHub Actions (매일 KST 23:00)
- **프론트엔드**: GitHub Pages (정적 HTML/CSS/JS)

## 🚀 로컬 실행

```bash
pip install gurobipy
python main.py                                    # 콘솔 출력
python main.py --output docs/data/result.json     # JSON 저장
python main.py --team Samsung                     # 특정 팀만
```

## 📝 License

MIT
