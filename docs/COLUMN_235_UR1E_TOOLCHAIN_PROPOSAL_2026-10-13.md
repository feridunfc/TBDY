# UR-1E — iki satırlık toolchain önerisi / UYGULANMADI

Kaynak/test düzeltmesi HEAD52f466b56f6bf4786fb0d0e4c7c8eebcf585e1fa. Üç fixture
import'u çözüldü; actualGitHub zero-new gate şimdi farklı iki kurulum eksikliğini
kanıtlıyor. [Özgün run](https://github.com/feridunfc/TBDY/actions/runs/38440754071),
job115446385850: candidate1141PASS/8FAIL/39SKIP; base1022PASS/2FAIL;6newFAIL.
Bunlar gerçek FAIL kalır; skip/ignore/guard allowance yapılmaz.

- Üç PDFcase: ModuleNotFoundError reportlab. Existing requirements-column-v2.txt
  ReportLab4.4.9 ister; report kodu bunu import eder. Sourcefile blob
  5165b35869beb0083e07dd48c4d999988cc7a1b8 doğrulandı.
- Üç launcher case: CI3.11, değişmeyen tools/start_column_product.py minimum3.12
  guard'ında duruyor. Foreignvenv/installfailure/usedport assertion'ına ulaşmıyor.
  Launcher blob811134e309a0926b7a6240c04d40bde82599eb07 doğrulandı; pin düşürülmez.

**Öneri yalnız CI kurulumunu mevcut ürün profiliyle uyumlar. UYGULANMADI.**
Protected source workflow blob05a197ffa2c4544bcb7355d2c8805bd7183df473.

```diff
--- a/.github/workflows/ur_1e_validation.yml
+++ b/.github/workflows/ur_1e_validation.yml
@@
-          python-version: "3.11"
+          python-version: "3.12"
@@
             jsonschema \\
+            reportlab==4.4.9 \\
             weasyprint==69.0 \\
```

Zero-new comparison script, baseline selection, exception expectations, owner
integration assertion'ları, native gates ve production pins değişmez. Bu
önerinin guard gevşetme amacı yoktur; actual2baseFAIL/new6FAIL aynı şekilde
karşılaştırılmalıdır.

## Neden ayrı supervisor kararı gerekiyor

Yüklenen COLUMN_235_ABI7_SUPERVISOR_PACKAGE_REVIEW_2026-10-13(1).md talimatı:
“accepted kimlikleri/protected45/same6 architecture koru.” UR-1E workflow'u bu45
hash yüzeyinin biridir. Yukarıdaki iki satır o tek hash'i değiştirir;0/45 drift
olarak raporlanamaz. Protectedworkflow toolchain-only değişiklik için açık
istisna ve bağımsız yeni hash qualification kararı olmadan uygulanmaz. Diğer44
surface ve workflow zero-new guard byte'ları korunmalıdır. Mevcut45sourcebound
hash ledger'i silinmez veya kendiliğinden yeniden baseline edilmez.

Onaydan sonra: çalışma ortamı yeniden bağlanmalı; source52/sondocsHEAD ve clean
worktree reconciliation; sadece iki setup satırı; actual3.12 installed toolchain
coldcollection/realbroad/fresh exact PRbase zero-new gate; private2404kimlik,
owner24nonbrowsercase ve profilecase ayrı; compile/import/diff ve same6arch;
coherentPASS commit/push. Yeni originalXML/log olmadan2404fullPASS iddiası yok.

## Operator / model sınırı

ABI7 orijinal paket/head9f426f5/treec557a517/SHA2ea359…82e değişmedi. Bu CI
kurulum önerisi operator repin, livecoordinate veya source mutation yetkisi
vermez. WORKER_ETABSNO; LIVE_AUTHNONE; MERGENO; FC09UNCHANGED;
GLOBALDELTANOTPROVEN; M6_BOPEN; R2NO.
