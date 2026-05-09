# -*- coding: utf-8 -*-
"""Kemikalieskatt declaration wizard + report data builder.

Aggregates posted customer-invoice and credit-note lines that carry a
``swedish_excise`` tax linked to a Kemikalieskatt-type
``excise.tax.type`` (i.e. ``has_reduction_levels=True``), grouped by
the type and the per-line reduction level. Output mirrors what
Skatteverket asks for on the *Punktskattedeklaration — Skatt på
kemikalier i viss elektronik* (e-tjänst, replaces the SKV 5320
paper form): bruttoredovisning per varugrupp + avdrag 50/95 % +
nettobelopp.

Calculation is driven by the per-line snapshot fields
(``excise_weight``, ``excise_reduction_ratio``) so historical
invoices stay frozen at the rate / reduction values they had at
posting time — exactly the audit-trail behaviour Skatteverket
expects.
"""
from collections import defaultdict
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError


# Map snapshot ratio (1.0 / 0.5 / 0.05) → declaration bucket key.
# Rounded to 2 decimals before the lookup so that line-level fp
# noise doesn't mis-bucket a rate.
_RATIO_TO_REDUCTION = {
    1.00: '0',    # No reduction — full rate paid
    0.50: '50',   # 50 % deduction
    0.05: '95',   # 95 % deduction
}
_REDUCTION_PCT_LABEL = {
    '0': '0 % avdrag (full skatt)',
    '50': '50 % avdrag',
    '95': '95 % avdrag',
}


class ExciseDeclarationWizard(models.TransientModel):
    """One-shot wizard: pick a period, then preview / print the
    Kemikalieskatt declaration.

    The wizard doubles as the report's data carrier — the QWeb PDF
    template iterates over ``self`` to render. Keeping computation
    on the wizard (instead of in a separate stored model) means the
    report always reflects the current state of the database, with
    no risk of stale snapshots.
    """

    _name = 'excise.declaration.wizard'
    _description = 'Excise Tax Declaration (Kemikalieskatt)'

    company_id = fields.Many2one(
        'res.company',
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    date_from = fields.Date(
        string="From Date",
        required=True,
        default=lambda self: date.today().replace(day=1),
        help="Period start. Posted customer invoices and credit "
             "notes with an Invoice Date on or after this date are "
             "included.",
    )
    date_to = fields.Date(
        string="To Date",
        required=True,
        default=lambda self: date.today(),
        help="Period end (inclusive). Defaults to today; for a "
             "monthly Skatteverket declaration set this to the last "
             "day of the period being declared.",
    )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for w in self:
            if w.date_from and w.date_to and w.date_from > w.date_to:
                raise UserError(_(
                    "From Date (%(from)s) must be on or before "
                    "To Date (%(to)s)."
                ) % {'from': w.date_from, 'to': w.date_to})

    # ------------------------------------------------------------------
    # Action buttons
    # ------------------------------------------------------------------
    def action_view_report(self):
        """Open the wizard's result form view (read-only summary)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'excise.declaration.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'view_id': self.env.ref(
                'l10n_se_excise_tax.view_excise_declaration_result_form'
            ).id,
            'target': 'new',
            'name': _("Kemikalieskatt — Declaration Preview"),
        }

    def action_print_report(self):
        """Render the QWeb PDF for the selected period."""
        self.ensure_one()
        return self.env.ref(
            'l10n_se_excise_tax.action_report_kemikalieskatt_declaration'
        ).report_action(self)

    # ------------------------------------------------------------------
    # Data aggregation
    # ------------------------------------------------------------------
    def _get_kemikalieskatt_lines_domain(self):
        """Return the search domain for invoice lines that should
        contribute to the Kemikalieskatt declaration.

        Filters:
        * Posted customer invoice / credit note (refunds are added
          with their natural sign so a credit note reduces the
          period's total).
        * Same company as the wizard.
        * Invoice Date inside the period (Skatteverket reporting is
          driven by ``invoice_date``, not posting date — that's the
          tax point per Lag (2016:1067) §15).
        * Real product line (no notes, sections, payment terms).
        * Carries at least one ``swedish_excise`` tax linked to an
          ``excise.tax.type`` with ``has_reduction_levels=True``
          (i.e. Kemikalieskatt; nicotine and tobacco are out of
          scope for this report).
        """
        self.ensure_one()
        return [
            ('parent_state', '=', 'posted'),
            ('move_id.move_type', 'in', ('out_invoice', 'out_refund')),
            ('move_id.company_id', '=', self.company_id.id),
            ('move_id.invoice_date', '>=', self.date_from),
            ('move_id.invoice_date', '<=', self.date_to),
            ('display_type', '=', 'product'),
            ('tax_ids.amount_type', '=', 'swedish_excise'),
            ('tax_ids.excise_type_id.has_reduction_levels', '=', True),
        ]

    def _compute_kemikalieskatt_declaration(self):
        """Aggregate the period's Kemikalieskatt snapshots.

        Walks each contributing ``account.move.line``, recomputes
        brutto / avdrag / netto from the snapshot fields (so the
        engine's per-line cap is applied identically to what was
        actually charged), and groups the result by (excise type,
        reduction bucket).

        Refunds (``out_refund``) carry positive ``quantity`` in
        Odoo 19's data model but represent a negative contribution
        to the period — multiply by ``-1`` so a credit note reduces
        the declared total exactly the way Skatteverket expects.

        Returns a list of per-excise-type dicts:
            [
              {
                'excise_type': <excise.tax.type record>,
                'tax_rate': 180.71,
                'max_limit': 552.27,
                'reductions': {
                  '0':  {'kg': ..., 'brutto': ..., 'avdrag': ..., 'netto': ..., 'lines': N, 'cap_hits': M},
                  '50': {...},
                  '95': {...},
                },
                'kg':     <total weight, all reductions>,
                'brutto': <total brutto, all reductions>,
                'avdrag': <total avdrag>,
                'netto':  <total netto = sum payable for this group>,
                'lines':  <total contributing invoice lines>,
                'cap_hits': <how many lines hit the per-unit cap>,
              },
              ...
            ]
        and a separate ``grand_total`` (sum of every type's netto).
        """
        self.ensure_one()
        AccountMoveLine = self.env['account.move.line']
        lines = AccountMoveLine.search(
            self._get_kemikalieskatt_lines_domain()
        )

        # Two-level dict: excise_type_id → reduction_pct → totals.
        per_type = defaultdict(lambda: {
            'excise_type': None,
            'tax_rate': 0.0,
            'max_limit': 0.0,
            'reductions': defaultdict(lambda: {
                'kg': 0.0, 'brutto': 0.0, 'avdrag': 0.0,
                'netto': 0.0, 'lines': 0, 'cap_hits': 0,
            }),
            'kg': 0.0, 'brutto': 0.0, 'avdrag': 0.0,
            'netto': 0.0, 'lines': 0, 'cap_hits': 0,
        })

        for line in lines:
            # First Kemikalieskatt-style swedish_excise tax on the
            # line. Mirrors the engine's "[:1]" pick in
            # _compute_excise_amount_per_unit and keeps the report
            # aligned with what was actually charged.
            excise_tax = line.tax_ids.filtered(
                lambda t: (
                    t.amount_type == 'swedish_excise'
                    and t.excise_type_id
                    and t.excise_type_id.has_reduction_levels
                )
            )[:1]
            if not excise_tax:
                continue
            etype = excise_tax.excise_type_id
            weight_per_unit = line.excise_weight or 0.0
            if weight_per_unit <= 0.0:
                # Snapshot weight is the source of truth — a zero
                # there means this line wasn't actually carrying
                # excise (e.g. an AWK customer or a foreign sale,
                # both of which neutralise the snapshot at posting
                # time). Skip silently rather than mis-report.
                continue

            ratio = round(line.excise_reduction_ratio or 1.0, 2)
            red_key = _RATIO_TO_REDUCTION.get(ratio)
            if red_key is None:
                # Unknown ratio (e.g. legacy 0.10 from pre-19.0.5
                # databases that somehow escaped the migration).
                # Bucket it as '0' so the math still adds up; the
                # cap_hits / lines counters still count it.
                red_key = '0'

            qty = abs(line.quantity)
            sign = -1 if line.move_id.move_type == 'out_refund' else 1
            kg = sign * weight_per_unit * qty

            # Per-unit gross, with the Kemikalieskatt cap applied.
            per_unit_raw = weight_per_unit * etype.tax_rate
            cap_hit = (
                etype.max_limit > 0.0 and per_unit_raw > etype.max_limit
            )
            per_unit_capped = (
                etype.max_limit if cap_hit else per_unit_raw
            )
            brutto = sign * per_unit_capped * qty
            netto = brutto * ratio
            avdrag = brutto - netto

            type_bucket = per_type[etype.id]
            type_bucket['excise_type'] = etype
            type_bucket['tax_rate'] = etype.tax_rate
            type_bucket['max_limit'] = etype.max_limit

            red_bucket = type_bucket['reductions'][red_key]
            red_bucket['kg'] += kg
            red_bucket['brutto'] += brutto
            red_bucket['avdrag'] += avdrag
            red_bucket['netto'] += netto
            red_bucket['lines'] += 1
            if cap_hit:
                red_bucket['cap_hits'] += int(qty)

            type_bucket['kg'] += kg
            type_bucket['brutto'] += brutto
            type_bucket['avdrag'] += avdrag
            type_bucket['netto'] += netto
            type_bucket['lines'] += 1
            if cap_hit:
                type_bucket['cap_hits'] += int(qty)

        # Convert defaultdicts to plain dicts and add a stable
        # reduction-row order (0 → 50 → 95) that the QWeb template
        # can iterate without re-sorting.
        result_types = []
        for etype_id, bucket in per_type.items():
            ordered_reductions = []
            for key in ('0', '50', '95'):
                if key in bucket['reductions']:
                    row = dict(bucket['reductions'][key])
                    row['key'] = key
                    row['label'] = _REDUCTION_PCT_LABEL[key]
                    ordered_reductions.append(row)
            bucket['reductions'] = ordered_reductions
            result_types.append(bucket)

        # Stable order: by excise_type sequence (id is fine here —
        # shipped data assigns lower ids to high-rate first).
        result_types.sort(key=lambda b: b['excise_type'].id)

        grand_total = sum(b['netto'] for b in result_types)
        return result_types, grand_total

    # ------------------------------------------------------------------
    # Computed read-only fields used by the result form view.
    # ------------------------------------------------------------------
    declaration_summary = fields.Html(
        compute='_compute_declaration_preview',
        string="Declaration Summary",
        sanitize=False,
        help="Read-only preview of the Skatteverket declaration "
             "for the selected period. Recomputes on every read so "
             "edits to underlying invoices are reflected immediately.",
    )
    grand_total_payable = fields.Monetary(
        compute='_compute_declaration_preview',
        string="Total Payable (SEK)",
        currency_field='currency_id',
        help="Sum of net excise tax to be reported in the period.",
    )
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        readonly=True,
    )

    @api.depends('date_from', 'date_to', 'company_id')
    def _compute_declaration_preview(self):
        for w in self:
            if not (w.date_from and w.date_to and w.company_id):
                w.declaration_summary = False
                w.grand_total_payable = 0.0
                continue
            types, grand = w._compute_declaration_preview_render()
            w.declaration_summary = types
            w.grand_total_payable = grand

    def _compute_declaration_preview_render(self):
        """Render the same data the PDF report uses, as an HTML
        snippet that the result form can show inline (so the user
        sees the numbers before clicking Print).
        """
        self.ensure_one()
        types, grand_total = self._compute_kemikalieskatt_declaration()
        if not types:
            return ('<p class="text-muted">'
                    + _("No posted Kemikalieskatt invoices in the "
                        "selected period.")
                    + '</p>'), 0.0

        rows = []
        rows.append(
            '<table class="table table-sm" '
            'style="width:auto;min-width:560px;">'
        )
        rows.append(
            '<thead><tr>'
            '<th>' + _("Product Group") + '</th>'
            '<th>' + _("Reduction") + '</th>'
            '<th class="text-end">' + _("Weight (kg)") + '</th>'
            '<th class="text-end">' + _("Brutto (SEK)") + '</th>'
            '<th class="text-end">' + _("Avdrag (SEK)") + '</th>'
            '<th class="text-end">' + _("Netto (SEK)") + '</th>'
            '<th class="text-end">' + _("Lines") + '</th>'
            '</tr></thead><tbody>'
        )
        for t in types:
            first = True
            for red in t['reductions']:
                rows.append('<tr>')
                if first:
                    rows.append(
                        '<td rowspan="%d"><strong>%s</strong><br/>'
                        '<small class="text-muted">%s kr/kg, '
                        'tak %s kr/styck</small></td>' % (
                            len(t['reductions']),
                            t['excise_type'].name,
                            ('%.2f' % t['tax_rate']).replace('.', ','),
                            ('%.2f' % t['max_limit']).replace('.', ','),
                        )
                    )
                    first = False
                rows.append('<td>%s</td>' % red['label'])
                rows.append('<td class="text-end">%s</td>' % (
                    ('%.3f' % red['kg']).replace('.', ',')))
                rows.append('<td class="text-end">%s</td>' % (
                    ('%.2f' % red['brutto']).replace('.', ',')))
                rows.append('<td class="text-end">%s</td>' % (
                    ('%.2f' % red['avdrag']).replace('.', ',')))
                rows.append('<td class="text-end"><strong>%s</strong></td>' % (
                    ('%.2f' % red['netto']).replace('.', ',')))
                rows.append('<td class="text-end">%d</td>' % red['lines'])
                rows.append('</tr>')
            # Sub-total row per type.
            rows.append(
                '<tr style="background:#f0f0f0;">'
                '<td></td><td><em>' + _("Sub-total") + '</em></td>'
                '<td class="text-end"><em>%s</em></td>'
                '<td class="text-end"><em>%s</em></td>'
                '<td class="text-end"><em>%s</em></td>'
                '<td class="text-end"><strong>%s</strong></td>'
                '<td class="text-end"><em>%d</em></td>'
                '</tr>' % (
                    ('%.3f' % t['kg']).replace('.', ','),
                    ('%.2f' % t['brutto']).replace('.', ','),
                    ('%.2f' % t['avdrag']).replace('.', ','),
                    ('%.2f' % t['netto']).replace('.', ','),
                    t['lines'],
                )
            )
        rows.append('</tbody></table>')
        return ''.join(rows), grand_total
