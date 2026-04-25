# Swedish Excise Tax (`l10n_se_excise_tax`)

Odoo 19 module that adds Swedish excise-tax handling to quotations, sales
orders and invoices. The first-phase scope is **Chemical Tax
(Kemikalieskatt)** on electronics and major appliances, but the design is
intended to generalise to every EU excise duty that is charged before VAT.

* **Version:** 19.0.1.4.0
* **License:** LGPL-3
* **Author:** Lasse Larsson
* **Category:** Accounting / Localizations
* **Depends on:** `account`, `product`, `sale`

---

## Why this module exists

Swedish excise taxes (punktskatter) are levied on specific goods and are
calculated **before** VAT; VAT is then charged on the sum of the line
subtotal and the excise amount. Standard Odoo tax types
(`percent` / `fixed` / `division`) cannot express the Swedish Chemical
Tax rule, which is:

    excise_per_unit = min(net_weight_kg * rate_sek_per_kg, max_limit_sek)

with an optional reduction of 50 % or 90 % per product.

This module plugs a new `amount_type = 'swedish_excise'` into Odoo's
rewritten tax engine, adds the per-product snapshot data the formula
needs, and wires the result into the standard VAT base so the final
invoice totals are correct end-to-end.

---

## Features

### Tax engine

* **Excise Tax Types** – a lightweight master data model
  (`excise.tax.type`) holding the per-kg rate and the maximum per-unit
  cap. Two demo types ship with the module: *Electronics (High Rate)*
  at 114 SEK/kg and *Major Appliances (Low Rate)* at 11 SEK/kg, both
  capped at 562 SEK/unit.
* **Product configuration** – on each product template you can flag it
  as excise-taxable, pick an excise type, enter the excise weight, and
  select a reduction level (0 %, 50 % or 90 %).
* **New tax kind** – `amount_type = 'swedish_excise'` on `account.tax`,
  with a Many2one to the excise type and related inline-editable
  rate/cap fields.
* **Tax-engine integration** – overrides Odoo 19's
  `_eval_tax_amount_fixed_amount` so the engine produces a correct
  per-line excise amount for our custom type. A per-line snapshot
  (weight + reduction factor) is propagated through the tax recordset
  via context.
* **VAT compounding done right** – the excise tax has
  `include_base_amount=True` and ships at `sequence=0`, so it sorts
  strictly before standard Swedish 25 % VAT (sequence 1) and Odoo's
  cascade forwards the excise into the VAT base. VAT is computed on
  `(line subtotal + excise)`, as required by Skatteverket.
* **Snapshot on the lines** – both `sale.order.line` and
  `account.move.line` store the excise weight and reduction ratio that
  were in effect when the line was created, so later edits on the
  product template don't retroactively change confirmed orders or
  posted invoices.

### Customer-facing presentation

* **"Show Excise Tax as Separate Row" company toggle.** When ON
  (default), the customer-facing PDF, customer portal and form view
  all show the full breakdown:
  *Untaxed Amount → Swedish Excise Tax → VAT → Total*. When OFF, the
  customer-facing PDF and portal *fold* the excise into the line
  prices: per-line **Unit Price** and **Amount** columns show the
  excise-inclusive value, and the totals block collapses to
  *Untaxed (incl. excise) → VAT → Total*. The form view (the seller's
  editing surface) always shows the full breakdown regardless of this
  flag.
* **"Hide VAT Column on Documents" company toggle.** Hides the
  per-line Moms / VAT / Taxes column (the column that shows labels
  like `25% G CHEM E`) on the customer-facing PDF and portal. The VAT
  *row* in the totals block stays visible — the Swedish invoice
  disclosure is preserved by the totals row, not the per-line column.

### Customer exemption

* **Approved Warehouse Keeper (`Godkänd lagerhållare`).** A boolean on
  `res.partner`. When ticked, the Swedish chemical excise tax is **not
  computed** on lines billed to that customer — the AWK declares and
  pays the tax themselves under the deferred-duty regime when they
  resell to a non-AWK end customer.
* **Foreign customers exempt automatically.** If the customer's
  `country_id` is set and differs from the company's `country_id`,
  the excise is skipped. Swedish chemical tax is a domestic tax;
  exports do not carry it.

In both cases the excise tax is filtered out of the line's tax
computation entirely (no zero-amount tax row, no cascade), so the
customer-facing invoice / quotation reads exactly as if the excise
didn't apply.

### Posting & reporting

* **Automatic GL account binding** – at install time, a
  `post_init_hook` walks the chart and binds the first available BAS
  liability account to the excise tax repartition: `2616` (preferred,
  *Kemikalieskatt att betala*), `2615`, `2640` (*Övrig punktskatt*) or
  `2980` (*Övriga skatteskulder*).
* **Skatteverket reporting tags** – four `account.account.tag`
  records scoped to Sweden, following Odoo's `+`/`-` convention so
  refunds reverse the sign automatically:
  `±Kemikalieskatt – Underlag`, `±Kemikalieskatt – Skatt att betala`.
* **Tax closing integration** – the tax repartition lines are
  flagged `use_in_tax_closing = True`, so the amounts feed the
  standard Odoo tax closing entry.
* **Posting Setup summary** – the tax form shows, read-only, which GL
  account and which Skatteverket tags the tax is currently wired to,
  without having to scroll into the Definition tab.

---

## Architecture at a glance

```
   Product (is_excise_taxable, excise_tax_type_id,
            net_weight_excise, excise_reduction)
            │
            │  onchange  →  snapshot copied to the line
            ▼
   sale.order.line  /  account.move.line
       excise_weight, excise_reduction_ratio
            │
            │  _prepare_base_line_for_taxes_computation
            │     ├─ if partner exempt (AWK or foreign):
            │     │    drop swedish_excise from base_line.tax_ids
            │     └─ else:
            │          base_line['tax_ids'] = tax_ids.with_context(
            │              excise_line_vals={weight, reduction_ratio})
            ▼
   account.tax (amount_type='swedish_excise', sequence=0,
                include_base_amount=True,
                tax_group_id = Swedish Excise Tax)
            │
            │  _eval_tax_amount_fixed_amount
            │     └─ reads excise_line_vals from self.env.context,
            │        returns quantity * min(weight*rate, cap) * reduction
            │
            │  Odoo's standard cascade (_propagate_extra_taxes_base)
            │     └─ forwards the excise amount into VAT's base
            ▼
   VAT computes on (subtotal + excise) → VAT row in totals
            │
            ▼
   tax_totals JSON (form view: full breakdown always)
            │
            │  QWeb PDF / portal:
            │     └─ ._l10n_se_get_tax_totals_for_render() applies
            │        the customer-facing fold per company flag
            ▼
   Invoice repartition lines (posting)
       base line  → tag: ±Kemikalieskatt – Underlag
       tax  line  → tag: ±Kemikalieskatt – Skatt att betala,
                    account_id = BAS 2616/2615/2640/2980,
                    use_in_tax_closing = True
```

---

## Installation

1. Drop the module in an Odoo 19 addons path.
2. Update the app list and install **Swedish Excise Tax (Chemical Tax)**.

The `post_init_hook` runs once at install and binds the first BAS
liability account it finds on each company
(`2616 → 2615 → 2640 → 2980`) to the tax-type repartition lines. If
none exist, it logs a notice and the accountant is expected to assign
the account manually on the tax form.

### Updating an existing install

**Always use the CLI upgrade path, not the web-UI Upgrade button**:

```bash
docker compose stop odoo
docker compose run --rm odoo odoo -d <db> -u l10n_se_excise_tax --stop-after-init
docker compose start odoo
```

(or the equivalent without docker:
`odoo -c /etc/odoo/odoo.conf -d <db> -u l10n_se_excise_tax --stop-after-init`).

Migrations in `migrations/` run during `-u`, before Odoo touches any
schema. The web-UI Upgrade button does a pre-flight query on
`res.company` *before* migrations run, which can fail with
`psycopg2.errors.UndefinedColumn` whenever the upgrade renames a
stored column. If you ever do hit that error, the recovery is one
SQL statement; see HANDOFF section 8 for the exact form depending on
where you came from.

> ⚠️ **`noupdate="1"` caveat.** `data/excise_tax_data.xml` is declared
> `noupdate="1"` so accountant-side customisations survive upgrades.
> The side-effect is that field changes on the shipped tax records
> (e.g. the 19.0.1.3.1 sequence change) do **not** apply on plain
> `-u` for existing databases. The relevant migration scripts in
> `migrations/<version>/` apply those changes via SQL on already-
> installed records.

---

## Configuration

### Excise Tax Types

*Accounting → Configuration → Excise Tax Types*

Maintain the rate (SEK/kg) and max cap per excise type. Confirmed
orders and posted invoices are immune to later rate changes because
they carry a snapshot.

### Products

On the product template, enable **Excise Taxable** and fill in:

* **Excise Tax Type** – the rate/cap row to use
* **Excise Tax Weight (kg)** – the weight that drives the calculation
* **Reduction Level** – 0 % (full), 50 % or 90 %

Finally, add the matching `account.tax` (e.g. *Chemical Tax
(Electronics)* — internal name `CHEM E`) to the product's **Customer
Taxes** alongside VAT.

### Tax form

Each excise tax shows:

* Linked **Excise Type** (with inline-editable rate and cap).
* **Posting Setup** block — read-only summary of the GL account and
  Skatteverket tags derived from the Definition tab.

### Per-line overrides

On the sale order and invoice line, `Excise Weight` and
`Excise Reduction Ratio` are editable (hidden columns by default, shown
via the optional-column selector). This lets the accountant tweak a
specific document without changing the product master.

### Company-level display toggles

*Accounting → Configuration → Settings → Swedish Excise Tax*

* **Show Excise Tax as Separate Row.** Default ON. See the *Features*
  section above for the effect.
* **Hide VAT Column on Documents.** Default OFF. Hides the Moms /
  Taxes column from the customer-facing PDF and portal.

### Customer-level exemption

*Sales / Accounting → Customers → open a partner → Sales & Purchase tab*

* **Approved Warehouse Keeper.** Default OFF. Tick this on customers
  registered with Skatteverket as `Godkänd lagerhållare`.

Customers based in another country (the `Country` field on the
customer record differs from the company's country) are exempt
automatically — no per-customer flag needed.

---

## Posting & reporting

* **GL account** – automatically bound to the first available BAS
  liability account per company: `2616` (preferred, *Kemikalieskatt
  att betala*), `2615`, `2640` (*Övrig punktskatt*) or `2980`
  (*Övriga skatteskulder*).
* **Skatteverket tags** – four `account.account.tag` records scoped to
  Sweden (`country_id = base.se`, `applicability = taxes`), following
  Odoo's `+`/`-` convention so refunds reverse the sign automatically:
  `±Kemikalieskatt – Underlag`, `±Kemikalieskatt – Skatt att betala`.
* **Tax closing** – the tax repartition lines are flagged
  `use_in_tax_closing = True`, so the amounts feed the standard Odoo
  tax closing entry.

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
│   └── 19.0.1.3.1/post-migration.py
├── models/
│   ├── __init__.py
│   ├── account_move.py         # _l10n_se_get_tax_totals_for_render
│   ├── account_move_line.py    # invoice-line snapshot, base-line hook,
│   │                           #   display-price computed fields
│   ├── account_tax.py          # swedish_excise amount type, _eval hook,
│   │                           #   _l10n_se_excise_postprocess_tax_totals
│   ├── excise_tax.py           # excise.tax.type + product.template fields
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
    ├── product_views.xml           # product template + excise.tax.type
    ├── report_templates.xml        # QWeb inherits for sale PDF / portal
    │                               #   and invoice PDF: per-line column
    │                               #   swap, Taxes-column hide, totals fold
    ├── res_config_settings_views.xml
    ├── res_partner_views.xml       # AWK checkbox on partner form
    └── sale_order_views.xml        # SO-line excise columns
```

---

## Known limits / roadmap

* **Scope.** Only Swedish Chemical Tax is shipped out of the box. The
  engine is generic (weight × rate, capped, optional reduction) and
  should cover most weight- or unit-based excise duties in the EU. To
  add a new country/duty:
  1. Add `excise.tax.type` records with the country-specific rate/cap.
  2. Add `account.account.tag` records with `country_id` set to the
     target country and the local reporting box codes.
  3. Add `account.tax` records pointing at the new excise type and
     tags, in a country-scoped data file. Make sure the `sequence`
     is strictly lower than the country's standard VAT sequence —
     otherwise the include_base_amount cascade silently won't fire.
  4. Add the target country's liability account code(s) to
     `hooks._CANDIDATE_CODES` (or refactor the hook to read them from
     a per-country mapping).
* **Multi-company.** The hook searches the BAS account in each
  company's chart separately, but the data-file tags are global (they
  carry `country_id = base.se`). That is fine for SE-only tenants and
  will need country scoping once non-SE data is added.
* **Tests.** The current test coverage is manual (SO → invoice round
  trip, exemption matrix). A future release should add an automated
  `tests/test_excise_chemical.py` covering weight × rate, cap,
  reduction, VAT compounding, refund sign flipping, and the AWK /
  foreign-customer exemption.
* **AWK is currently a flat boolean.** Could be extended to a date
  range so historical documents reflect the partner's status at the
  time of sale rather than the current state.

---

## Acknowledgements

Developed against Odoo 19. Designed to play nicely with the Swedish
Accounting localization (`l10n_se*`) and with Odoo's tax-closing and
tax-reports workflow. Contributions extending the module to other EU
excise regimes are welcome.
