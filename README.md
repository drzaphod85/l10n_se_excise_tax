# Swedish Excise Tax (`l10n_se_excise_tax`)

Odoo 19 module that adds Swedish excise-tax handling to quotations,
sales orders and invoices. The supported taxes today are:

- **Kemikalieskatt** (Chemical Tax) on certain electronics and
  major appliances.
- **Tobaksskatt** (Tobacco Tax) on cigarettes (per piece), cigars
  / cigarillos (per piece), snus, smoking tobacco, chewing tobacco
  and other tobacco products (per kg).
- **Nikotinskatt** (Nicotine Tax) on e-liquids (regular and
  high-concentration) and other nicotine products (white snus,
  pouches, etc.).

The architecture is generic — see [Adding a new excise
tax](#adding-a-new-excise-tax) at the bottom — so adding alcohol,
gravel, energy, or any other weight- / volume- / piece-based
excise regime is largely a data-file exercise rather than a code
change.

* **Version:** 19.0.3.3.2
* **License:** LGPL-3
* **Author:** Lasse Larsson
* **Category:** Accounting / Localizations
* **Depends on:** `account`, `product`, `sale`

---

## Why this module exists

Swedish excise taxes (punktskatter) are levied on specific goods and
are calculated **before** VAT; VAT is then charged on the sum of the
line subtotal and the excise amount. Standard Odoo tax types
(`percent` / `fixed` / `division`) cannot express the rules of
Kemikalieskatt or Nikotinskatt because they need a per-unit driver
(weight in kg or volume in litres) that varies per product, plus
optional caps and reductions.

This module:

1. Plugs a new `amount_type = 'swedish_excise'` into Odoo's tax
   engine so the engine can produce a non-zero amount for
   weight- / volume-based excise.
2. Generalises the per-unit calculation through a `unit_basis`
   selection on `excise.tax.type` (`kg` and `liter` ship today;
   `tonne`, `liter_pure`, `pcs`, … are easy to add).
3. Wires the result into the standard VAT base via Odoo's
   `include_base_amount` cascade so VAT computes on
   `subtotal + excise` exactly as Skatteverket requires.
4. Posts the excise to the right BAS liability account per company
   (chosen automatically at install time per a candidate chain that
   varies by tax category).

---

## Features

### Tax engine

* **`amount_type = 'swedish_excise'`** on `account.tax`, with a
  Many2one to an `excise.tax.type` that holds the rate and unit
  basis. Editing the rate / cap on the tax form propagates to the
  underlying type.
* **Per-product driver fields** (kg, litres) on `product.template`,
  with the right one auto-shown based on the linked
  `excise.tax.type`'s `unit_basis`.
* **Per-line snapshot** of `excise_weight` / `excise_volume` /
  `excise_reduction_ratio` on `sale.order.line` and
  `account.move.line` — confirmed orders and posted invoices keep
  the values they had at validation time, so later edits on the
  product template don't retroactively change historical documents.
* **Per-product reduction (Kemikalieskatt only)** — products with
  certain flame-retardant chemistries qualify for a 50 % or 95 %
  reduction (per Lag (2016:1067): 50 % when the product contains no
  bromine or chlorine compounds; 95 % when it also contains no
  phosphorus compounds). Enabled by ticking `has_reduction_levels`
  on the excise type; other excise regimes ignore the reduction
  field.
* **Default rules per product category.** The
  `excise.tax.default` model lets accountants set "products in
  category X default to this excise tax with this reduction" or
  fall back to an "all products" rule. Products inherit the
  configuration when first flagged Excise Taxable, and the
  *Apply Excise Defaults* server action retro-applies the rules
  to a selection of existing products. See
  *Configuration → Default Excise Tax Rules* below.
* **VAT compounding done right.** Excise ships at `sequence=0` so it
  sorts strictly before standard Swedish 25 % VAT (`sequence=1`),
  and Odoo's cascade forwards the excise amount into the VAT base.
  VAT is computed on `(line subtotal + excise)`.

### Customer-facing presentation

The module covers four customer-facing surfaces consistently —
the back-office sale-order / invoice form, the QWeb PDF report,
the customer portal, and the **eCommerce shop** (`/shop/product/<id>`,
`/shop/cart`, `/shop/checkout`). All four respect the company's
"Show Excise Tax as Separate Row" toggle and produce the same
math; they just present it differently:

- Form view always shows the full breakdown (seller's working surface).
- PDF / portal / eCommerce honour the company toggle: when OFF,
  the per-line Unit Price + Amount and the cart Subtotal display
  the excise-inclusive value; when ON, the excise itemises as a
  separate row and the line prices stay at the bare net value.

* **"Show Excise Tax as Separate Row" company toggle.** When ON
  (default), the customer-facing PDF, customer portal and form view
  all show the full breakdown:
  *Untaxed Amount → Swedish Excise Tax → VAT → Total*. When OFF,
  the customer-facing PDF and portal *fold* the excise into the line
  prices: per-line **Unit Price** and **Amount** columns show the
  excise-inclusive value, and the totals block collapses to
  *Untaxed (incl. excise) → VAT → Total*. The form view always
  shows the full breakdown regardless of this flag (it's the
  seller's editing surface).
* **"Hide VAT Column on Documents" company toggle.** Hides the
  per-line Moms / VAT / Taxes column (the column that shows labels
  like `25% G CHEM E`) on the customer-facing PDF and portal. The
  VAT *row* in the totals block stays visible — the Swedish invoice
  disclosure is preserved by the totals row, not the per-line
  column.

### Customer exemption

* **Approved Warehouse Keeper (`Godkänd lagerhållare`).** A boolean
  on `res.partner`. When ticked, every excise type (Kemikalieskatt,
  Nikotinskatt, …) is **not computed** on lines billed to that
  customer — the AWK declares and pays the tax themselves under the
  deferred-duty regime when they resell to a non-AWK end customer.
* **Foreign customers exempt automatically.** If the customer's
  `country_id` is set and differs from the company's `country_id`,
  the excise is skipped. Swedish excise is a domestic tax;
  exports do not carry it.

In both cases the excise tax is filtered out of the line's tax
computation entirely (no zero-amount tax row, no cascade), so the
customer-facing invoice / quotation reads exactly as if the excise
didn't apply.

### Posting & reporting

* **Automatic GL account binding per category.** At install time
  (and during version migrations that introduce new tax records), a
  hook walks each company's chart and binds the right BAS liability
  account to the excise tax's repartition. Candidate chains are
  defined per excise type:
  - Kemikalieskatt: `2616` → `2615` → `2640` → `2980`
    (`Kemikalieskatt att betala`, then VAT-series fallbacks, then
    `Övrig punktskatt`, then generic `Övriga skatteskulder`).
  - Nikotinskatt: `2640` → `2980` (no widely-accepted custom code
    for nicotine yet — sub-categorise via reporting tags).
  - Any new category added later defines its own chain.
* **Skatteverket reporting tags** — `account.account.tag` records
  scoped to Sweden, following Odoo's `+`/`-` convention so refunds
  reverse the sign automatically:
  - `±Kemikalieskatt - Underlag`, `±Kemikalieskatt - Skatt att betala`
  - `±Nikotinskatt - Underlag`, `±Nikotinskatt - Skatt att betala`
* **Tax-closing integration** — the tax repartition lines are
  flagged `use_in_tax_closing = True`, so the amounts feed the
  standard Odoo tax-closing entry.

---

## Architecture at a glance

```
   excise.tax.type
       ├── name (translatable)
       ├── country_id (default base.se)
       ├── unit_basis ∈ {kg, liter, …}
       ├── tax_rate (per unit_basis unit)
       ├── max_limit (per-unit cap; 0 = no cap)
       └── has_reduction_levels (Kemikalieskatt-style 50%/95%)
            ▲
            │ Many2one
            │
   account.tax (amount_type='swedish_excise', sequence=0,
                include_base_amount=True,
                tax_group_id = Swedish Excise Tax)

   Product (is_excise_taxable, excise_tax_type_id,
            net_weight_excise OR excise_volume_litres,
            excise_reduction)
            │
            │  onchange  →  snapshot copied to the line
            ▼
   sale.order.line  /  account.move.line
       excise_weight, excise_volume, excise_reduction_ratio
            │
            │  _prepare_base_line_for_taxes_computation
            │     ├─ if partner exempt (AWK or foreign):
            │     │    drop swedish_excise from base_line.tax_ids
            │     └─ else:
            │          base_line['tax_ids'] = tax_ids.with_context(
            │              excise_line_vals={weight, volume, reduction})
            ▼
   account.tax._eval_tax_amount_fixed_amount
       └─ dispatches on excise_type_id.unit_basis:
              'kg'    → weight × rate, capped, optional reduction
              'liter' → volume × rate
              'tonne' / 'pcs' / 'liter_pure' / … : add a branch when
                    you implement that regime (see "Adding a new
                    excise tax" below)
            │
            │  Odoo's standard cascade (_propagate_extra_taxes_base)
            │     └─ forwards the excise amount into VAT's base
            ▼
   VAT computes on (subtotal + excise) → VAT row in totals
            │
            ▼
   tax_totals JSON  ─►  form view: full breakdown always
                    │
                    └─►  PDF / portal: o._l10n_se_get_tax_totals_for_render()
                         applies the company-flag fold
            │
            ▼
   Invoice repartition lines (posting)
       base line  → tag: ±<TaxName> – Underlag
       tax  line  → tag: ±<TaxName> – Skatt att betala,
                    account_id = candidate-chain-bound BAS account,
                    use_in_tax_closing = True
```

---

## Installation

1. Drop the module in an Odoo 19 addons path.
2. Update the app list and install **Swedish Excise Tax (Chemical
   Tax)**.

The post-install hook runs once and binds the BAS liability accounts
per the candidate chains above. If none of the candidate codes exist
on a given company, the hook logs a notice and the accountant is
expected to assign the account manually on the tax form.

### Updating an existing install

**Always use the CLI upgrade path, not the web-UI Upgrade button**:

```bash
docker compose stop odoo
docker compose run --rm odoo odoo -d <db> -u l10n_se_excise_tax --stop-after-init
docker compose start odoo
```

(or, without docker:
`odoo -c /etc/odoo/odoo.conf -d <db> -u l10n_se_excise_tax --stop-after-init`).

Migrations in `migrations/<version>/` run during `-u`, before Odoo
touches schema. The web-UI Upgrade button does a pre-flight query on
`res.company` *before* migrations run, which can fail with
`psycopg2.errors.UndefinedColumn` if the upgrade renames a stored
column. The recovery is one SQL statement per affected column —
keep an eye on the version's migration script for the right `RENAME`.

> ⚠️ **`noupdate="1"` caveat.** `data/excise_tax_data.xml` is
> declared `noupdate="1"` so accountant-side customisations (changed
> rates, custom posting accounts, additional tags) survive upgrades.
> The side-effect is that field changes on the *shipped* records do
> **not** apply on plain `-u` for existing databases. The relevant
> migration scripts in `migrations/<version>/` apply those changes
> via SQL on already-installed records.

---

## Configuration

### Excise Tax Types

*Accounting → Configuration → Excise Tax Types*

Maintain the per-unit rate (SEK per kg, SEK per litre, etc.), the
per-unit cap, the unit basis, and whether the type uses
Kemikalieskatt-style reductions. Confirmed orders and posted
invoices are immune to later rate changes because they carry a
snapshot.

### Default Excise Tax Rules

*Accounting → Configuration → Default Excise Tax Rules*

Add rules that say *"products in this category default to this
excise tax with these settings"*. Each rule sets:

* **Product Category** — leave empty to make the rule apply to
  *all* products as a fallback. A category-specific rule always
  wins over the fallback.
* **Sequence** — multiple rules under the same scope are tried
  in ascending order (lowest first).
* **Default Excise Tax** — the `account.tax` (with
  `amount_type='swedish_excise'`) the rule pushes onto the
  product's Customer Taxes. The product's *Excise Tax Type* is
  derived from this tax.
* **Reduction Level** — only meaningful for types with
  `has_reduction_levels=True` (Kemikalieskatt). Hidden otherwise.

Rules are applied automatically when:

* a user toggles **Excise Taxable** on a product that has no
  excise type yet, or
* the product's **Internal Category** is changed and no excise
  is configured.

To retro-apply rules to a selection of *existing* products, pick
them in the product list and run *Action → Apply Excise Defaults*.
The action only touches products that aren't already configured
for excise, so it's safe to run repeatedly.

### Products

On the product template (Sales tab), enable **Excise Taxable** and
fill in:

* **Excise Tax Type** — picks the rate / cap / unit_basis row.
* **Excise Tax Weight (kg)** *(if the type's unit_basis is `kg`)*
  — used for Kemikalieskatt and "Nicotine — Other products".
* **Excise Tax Volume (L)** *(if the type's unit_basis is `liter`)*
  — used for Nicotine e-liquid (regular and high-concentration).
* **Reduction Level** *(only if the type has
  `has_reduction_levels=True` — i.e. Kemikalieskatt only)*: 0 %
  (full), 50 %, or 95 %. Per Lag (2016:1067): a product earns
  50 % if it contains no bromine or chlorine compounds, and 95 %
  if it also contains no phosphorus compounds.

Finally, add the matching `account.tax` to the product's **Customer
Taxes** alongside VAT:

| Tax (internal name) | Use for                                                      |
|---------------------|--------------------------------------------------------------|
| `CHEM E`            | High-rate Kemikalieskatt — most consumer electronics         |
| `CHEM M`            | Low-rate Kemikalieskatt — major appliances (vitvaror)        |
| `TOB CIG`           | Tobaksskatt on cigarettes (2.08 SEK/piece)                   |
| `TOB CGR`           | Tobaksskatt on cigars / cigarillos (1.83 SEK/piece)          |
| `TOB SNUS`          | Tobaksskatt on snus (435 SEK/kg)                             |
| `TOB RÖK`           | Tobaksskatt on smoking tobacco (2 525 SEK/kg)                |
| `TOB TUG`           | Tobaksskatt on chewing tobacco (598 SEK/kg)                  |
| `TOB ÖVR`           | Tobaksskatt on other tobacco (2 525 SEK/kg)                  |
| `NIK E-V`           | Nikotinskatt on regular e-liquid                             |
| `NIK E-V H`         | Nikotinskatt on high-concentration e-liquid                  |
| `NIK ÖVR`           | Nikotinskatt on other nicotine products (per kg)             |

> ℹ️ **Cigarette ad-valorem leg deferred.** Swedish cigarette tax
> is `2.08 SEK/piece + 1 % of retail price`. Only the per-piece
> leg (`TOB CIG`) ships in v1; the 1 % ad-valorem on retail price
> isn't supported because it requires a Skatteverket-set
> weighted-average price per product, not the actual line price.
> AWK distributors who need it can add a custom percent tax
> alongside `TOB CIG`.

### Tax form

Each excise tax shows:

* Linked **Excise Type** (with inline-editable rate / cap), the
  type's **Unit Basis**, and (for kg-based types) the **Max Limit
  per Unit**.
* **Posting Setup** block — read-only summary of the GL account
  and Skatteverket tags derived from the Definition tab.

### Per-line overrides

On the sale order and invoice line, `Excise Weight`, `Excise Volume`
and `Excise Reduction Ratio` are editable (hidden columns by default,
shown via the optional-column selector). This lets the accountant
tweak a specific document without changing the product master.

### Company-level display toggles

*Accounting → Configuration → Settings → Swedish Excise Tax*

* **Show Excise Tax as Separate Row.** Default ON.
* **Hide VAT Column on Documents.** Default OFF.
* **Excise Tax Types.** Shortcut button — opens
  *Configuration → Excise Tax Types*.
* **Default Excise Tax Rules.** Shortcut button — opens
  *Configuration → Default Excise Tax Rules*.

See the *Customer-facing presentation* section above for the effect
of each toggle.

### Customer-level exemption

*Sales / Accounting → Customers → open a partner → Sales & Purchase tab*

* **Approved Warehouse Keeper.** Default OFF. Tick this on customers
  registered with Skatteverket as `Godkänd lagerhållare`.

Customers based in another country are exempt automatically — no
per-customer flag needed.

---

## Module layout

```
l10n_se_excise_tax/
├── __init__.py                 # imports models + post_init_hook
├── __manifest__.py
├── hooks.py                    # BAS-account binder (post_init_hook)
├── README.md
├── data/
│   └── excise_tax_data.xml     # tax group, tags, excise types, taxes
├── migrations/
│   ├── 19.0.1.1.0/pre-migration.py
│   ├── 19.0.1.2.0/pre-migration.py
│   ├── 19.0.1.3.1/post-migration.py
│   ├── 19.0.2.0.0/post-migration.py
│   ├── 19.0.3.0.0/post-migration.py
│   ├── 19.0.3.4.0/post-migration.py   # apply_shipped_excise_data
│   ├── 19.0.4.0.0/post-migration.py   # apply_shipped_excise_data
│   └── 19.0.5.0.0/post-migration.py   # 90→95 reduction fix +
│                                      #   apply_shipped_excise_data
├── models/
│   ├── __init__.py
│   ├── account_move.py         # _l10n_se_get_tax_totals_for_render
│   ├── account_move_line.py    # invoice-line snapshot, base-line hook,
│   │                           #   display-price computed fields
│   ├── account_tax.py          # swedish_excise amount type, _eval hook,
│   │                           #   _l10n_se_excise_postprocess_tax_totals
│   ├── excise_tax.py           # excise.tax.type + product.template fields
│   │                           #   + _apply_excise_default /
│   │                           #     action_apply_excise_defaults
│   ├── excise_tax_default.py   # excise.tax.default — default-rule engine
│   ├── res_company.py          # display toggles
│   ├── res_config_settings.py  # related fields for the settings page
│   ├── res_partner.py          # AWK flag + _l10n_se_is_excise_exempt
│   ├── sale_order.py           # _l10n_se_get_tax_totals_for_render
│   └── sale_order_line.py      # sale-line snapshot, base-line hook,
│                               #   display-price computed fields
├── i18n/
│   └── sv.po                   # Swedish translations
├── security/
│   └── ir.model.access.csv
└── views/
    ├── account_move_views.xml      # invoice-line excise columns
    ├── account_tax_views.xml       # tax form: excise block + Posting Setup
    ├── excise_tax_default_views.xml # Default Excise Tax Rules
    │                               #   list/form/menu + "Apply Excise
    │                               #   Defaults" server action
    ├── product_views.xml           # product template + excise.tax.type
    ├── report_templates.xml        # QWeb inherits for sale PDF / portal
    │                               #   and invoice PDF: per-line column
    │                               #   swap, Taxes-column hide, totals fold
    ├── res_config_settings_views.xml
    ├── res_partner_views.xml       # AWK checkbox on partner form
    └── sale_order_views.xml        # SO-line excise columns
```

---

## Adding a new excise tax

The architecture is intentionally generic. Most new Swedish (or
EU-country) excise regimes can be added entirely from the data file
plus a tiny addition to the BAS-account candidate chain in `hooks.py`.
Below is a recipe; the worked example at the end implements
**Naturgrusskatt** (natural-gravel tax: 23 SEK/tonne flat, no cap,
no reduction).

### Step 1 — Pick a `unit_basis`

The shipped values are:

| `unit_basis` | What the engine reads from the line | Example                                |
|--------------|--------------------------------------|----------------------------------------|
| `kg`         | `excise_weight` (kg, snapshotted)    | Kemikalieskatt, snus, röktobak         |
| `liter`      | `excise_volume` (L, snapshotted)     | Nicotine e-liquid                      |
| `pcs`        | `excise_pieces` (count per product unit, snapshotted) | Cigarettes, cigars / cigarillos        |

If your tax needs a different driver (`tonne`, `liter_pure`, `m3`, …),
see Step 5 below — you'll add a new branch in
`account_tax.py::_get_excise_unit_amount` and a new per-product
field on `product.template`.

### Step 2 — Add the `excise.tax.type` record

In `data/excise_tax_data.xml`:

```xml
<record id="excise_type_my_new_tax" model="excise.tax.type">
    <field name="name">My New Excise Tax</field>
    <field name="country_id" ref="base.se"/>
    <field name="unit_basis">kg</field>           <!-- or 'liter' etc. -->
    <field name="tax_rate">42.00</field>          <!-- SEK per unit_basis unit -->
    <field name="max_limit">0.0</field>           <!-- 0 = no cap -->
    <field name="has_reduction_levels" eval="False"/>
    <!-- Set to True only if your tax has Kemikalieskatt-style
         50%/95% per-product reductions. -->
</record>
```

### Step 3 — Add the Skatteverket reporting tags

In the same data file, four `account.account.tag` records — one
each for invoice/refund × base/tax. Naming convention:
`±<TaxName> - Underlag` for the base, `±<TaxName> - Skatt att betala`
for the tax.

```xml
<record id="tag_my_new_tax_base_invoice" model="account.account.tag">
    <field name="name">+My New Excise - Underlag</field>
    <field name="applicability">taxes</field>
    <field name="country_id" ref="base.se"/>
</record>
<!-- + the three sibling records for tax/invoice, base/refund, tax/refund -->
```

### Step 4 — Add the `account.tax` record

```xml
<record id="tax_my_new_tax" model="account.tax">
    <field name="name">MY-TAX</field>
    <field name="type_tax_use">sale</field>
    <field name="amount_type">swedish_excise</field>
    <field name="amount">0.0</field>
    <field name="include_base_amount" eval="True"/>
    <field name="sequence">0</field>          <!-- MUST be < VAT -->
    <field name="description">My New Excise Tax</field>
    <field name="excise_type_id" ref="excise_type_my_new_tax"/>
    <field name="tax_group_id" ref="tax_group_excise"/>
    <field name="invoice_repartition_line_ids" eval="[
        (5, 0, 0),
        (0, 0, {'repartition_type': 'base', 'factor_percent': 100,
                'tag_ids': [(6, 0, [ref('tag_my_new_tax_base_invoice')])]}),
        (0, 0, {'repartition_type': 'tax', 'factor_percent': 100,
                'use_in_tax_closing': True,
                'tag_ids': [(6, 0, [ref('tag_my_new_tax_tax_invoice')])]}),
    ]"/>
    <field name="refund_repartition_line_ids" eval="[
        (5, 0, 0),
        (0, 0, {'repartition_type': 'base', 'factor_percent': 100,
                'tag_ids': [(6, 0, [ref('tag_my_new_tax_base_refund')])]}),
        (0, 0, {'repartition_type': 'tax', 'factor_percent': 100,
                'use_in_tax_closing': True,
                'tag_ids': [(6, 0, [ref('tag_my_new_tax_tax_refund')])]}),
    ]"/>
</record>
```

> ⚠️ **`sequence=0` is critical.** Standard Swedish 25 % VAT ships
> at sequence 1; if your excise tax sorts at the same sequence or
> higher, the engine processes VAT first and the
> `include_base_amount` cascade has nothing left to forward into.
> Symptom: VAT comes out at `25 % × subtotal` instead of
> `25 % × (subtotal + excise)` — silently wrong, no error.

### Step 5 — Wire the BAS-account candidate chain

In `hooks.py`, add an entry to `_CANDIDATES_BY_EXCISE_TYPE_XMLID`:

```python
_CANDIDATES_BY_EXCISE_TYPE_XMLID = {
    # … existing entries …
    'l10n_se_excise_tax.excise_type_my_new_tax': ('2640', '2980'),
    # Or whatever BAS chain is appropriate. Use your local chart.
}
```

If you skip this step, the tax falls back to `_DEFAULT_CANDIDATES`
(`2640` → `2980`) which is fine for most cases.

### Step 6 — (Optional) Add a new `unit_basis` value

If your tax can't be expressed as `kg` × rate or `liter` × rate
(e.g. cigarettes are per-piece, gravel is per-tonne, fuel is per-m³):

1. Add the new value to the `unit_basis` selection on
   `excise.tax.type` in `models/excise_tax.py`.
2. Add the matching per-product driver field on `product.template`
   in the same file (e.g. `excise_tonnes`, `excise_pieces_per_qty`).
3. Carry it through as a snapshot on `sale.order.line` and
   `account.move.line` — read in their
   `_prepare_base_line_for_taxes_computation` hooks and propagate
   through `excise_line_vals`.
4. Add the corresponding branch in
   `account_tax.py::_get_excise_unit_amount`:

   ```python
   if basis == 'tonne':
       if tonnes <= 0.0:
           return 0.0
       return tonnes * excise.tax_rate
   ```

5. Add a new conditional on `views/product_views.xml` so the right
   field shows up on the product form when this `unit_basis` is
   selected.

### Step 7 — Migration script (if your DB already has the module)

Because `data/excise_tax_data.xml` is `noupdate="1"`, a plain `-u`
will create the new tax/type/tag records on existing databases — but
won't overwrite any field on records that already exist. If you're
*editing* existing records (e.g. changing a rate), add a SQL update
to `migrations/<new-version>/post-migration.py`. See
`migrations/19.0.2.0.0/post-migration.py` for a working example
covering rate updates and a re-run of the BAS-account binding.

### Step 8 — Translations

Add Swedish entries to `i18n/sv.po` for the new tax type's `name`
field, the matching `account.tax.description`, and any new help
strings. Look at the Nikotinskatt entries for the exact structure.

### Worked example: Naturgrusskatt (23 SEK/tonne)

This is a per-tonne tax with no cap and no reduction. Most of the
recipe applies almost mechanically; the only piece that needs new
code is the `tonne` unit_basis in Step 6.

1. **`unit_basis = 'tonne'`** added to the selection on
   `excise.tax.type`.
2. **`excise_tonnes` field** added to `product.template`,
   snapshotted as `excise_tonnes` on the line models.
3. **`'tonne'` branch** added to `_get_excise_unit_amount`:
   `return tonnes * excise.tax_rate`.
4. **Data:** one `excise.tax.type` (rate 23, max_limit 0,
   `has_reduction_levels=False`), four reporting tags, one
   `account.tax` (`NATURGRUS`, sequence 0, include_base_amount=True).
5. **Hook:** `'l10n_se_excise_tax.excise_type_naturgrus':
   ('2640', '2980')` (no specific BAS code for gravel; follows
   "Övrig punktskatt" convention).
6. **Migration:** if shipping into an existing database, a
   `19.0.X.X.X/post-migration.py` to bind the BAS account on the
   newly-created `NATURGRUS` repartition lines.

The product form then automatically shows an *Excise Tonnes* field
when *Excise Tax Type* is set to *Naturgrusskatt*, and the engine
computes `tonnes × 23` per line, propagates into the VAT base via
`include_base_amount`, posts to BAS 2640 with
`±Naturgrusskatt – Skatt att betala` tags, and respects the AWK /
foreign-customer exemption out of the box.

---

## Known limits / roadmap

* **Scope.** Three excise regimes ship out of the box:
  Kemikalieskatt (electronics + major appliances),
  Nikotinskatt (e-liquid regular / high-concentration / other),
  and Tobaksskatt (cigarettes, cigars, snus, smoking, chewing,
  other). Alcohol, energy, gravel, pesticide, etc. fit the same
  architecture and can be added per the recipe above.
* **Compound taxes** (cigarettes: per-piece + ad-valorem) are best
  modelled as two separate `account.tax` records on the product —
  one `swedish_excise` for the per-piece leg, one standard
  `percent` for the ad-valorem leg. Both must have
  `sequence < VAT_sequence` for the cascade.
* **Multi-country.** `excise.tax.type.country_id` is in place, so
  the engine is ready for non-SE excises; the candidate-chain hook
  and the data-file pattern just need country-specific data.
* **Tests.** Coverage is currently manual. A future release should
  add `tests/test_excise_*.py` exercising the per-unit math, the
  cap, the reduction (Kemikalieskatt only), VAT compounding, refund
  sign flipping, and the AWK / foreign-customer exemption.
* **AWK is a flat boolean.** Could be extended to a date range so
  historical documents reflect the partner's status at the time of
  sale rather than the current state.

---

## Acknowledgements

Developed against Odoo 19. Designed to play nicely with the Swedish
Accounting localization (`l10n_se*`) and with Odoo's tax-closing and
tax-reports workflow. Contributions extending the module to other
Swedish excise regimes (or to other EU countries' excise systems)
are very welcome — please follow the recipe in [Adding a new excise
tax](#adding-a-new-excise-tax).
