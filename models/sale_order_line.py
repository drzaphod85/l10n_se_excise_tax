# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # ------------------------------------------------------------------
    # Snapshot fields – lock the excise basis at the moment the product
    # is picked so later changes on the product template don't retro-
    # actively change the quotation / order totals.
    #
    # These are stored compute fields with ``readonly=False``: the
    # compute fires whenever ``product_id`` changes (form view
    # onchange, programmatic ``create()``, eCommerce cart update,
    # API import — all of them), but the user / accountant can
    # still override per-line via the Excise Weight / Volume /
    # Pieces / Reduction Ratio columns surfaced on the order-line
    # list. The previous design relied on @api.onchange alone,
    # which only fires from the form view — eCommerce cart creation
    # therefore left the snapshot at zero, the engine computed
    # zero excise, and VAT silently fell back to ``25 % × subtotal``.
    # ------------------------------------------------------------------
    excise_weight = fields.Float(
        string="Excise Weight (kg)",
        digits='Stock Weight',
        compute='_compute_excise_snapshot',
        store=True,
        readonly=False,
        help="Weight (kg) used to calculate the Swedish excise tax for this "
             "line. Auto-populated from the product when selected; can be "
             "overridden per line. Only consulted when the linked Excise "
             "Type's Unit Basis is 'kg'.",
    )
    excise_volume = fields.Float(
        string="Excise Volume (L)",
        digits=(12, 4),
        compute='_compute_excise_snapshot',
        store=True,
        readonly=False,
        help="Volume (L) used to calculate the Swedish excise tax for "
             "this line. Auto-populated from the product when selected; "
             "can be overridden per line. Only consulted when the linked "
             "Excise Type's Unit Basis is 'liter'.",
    )
    excise_pieces = fields.Float(
        string="Excise Pieces (per unit)",
        digits=(12, 2),
        compute='_compute_excise_snapshot',
        store=True,
        readonly=False,
        help="Number of countable pieces per product unit (e.g. 20 for "
             "a 20-cigarette pack). Auto-populated from the product when "
             "selected; can be overridden per line. Only consulted when "
             "the linked Excise Type's Unit Basis is 'pcs'.",
    )
    excise_reduction_ratio = fields.Float(
        string="Excise Reduction Ratio",
        compute='_compute_excise_snapshot',
        store=True,
        readonly=False,
        help="Reduction factor applied to the weight-based excise amount. "
             "1.0 = full tax, 0.5 = 50% reduction, 0.1 = 90% reduction. "
             "Auto-populated from the product. Specific to Kemikalieskatt; "
             "non-kg excise types ignore it.",
    )

    @api.depends('product_id')
    def _compute_excise_snapshot(self):
        """Populate the per-line excise snapshot from the product.

        Replaces the older ``@api.onchange('product_id')`` populator
        — see the class-level comment block above for why. Fires on
        every code path that sets ``product_id``, including
        programmatic ``create()`` calls from eCommerce / cart /
        API / import.

        The fields are ``store=True, readonly=False`` so accountants
        can still override per line on the order. Once the user
        manually edits a snapshot the value sticks, because the
        compute only re-runs when ``product_id`` itself changes.
        """
        reduction_map = {'0': 1.0, '50': 0.5, '90': 0.1}
        for line in self:
            product = line.product_id
            if product and product.is_excise_taxable:
                line.excise_weight = product.net_weight_excise or 0.0
                line.excise_volume = product.excise_volume_litres or 0.0
                line.excise_pieces = product.excise_pieces_per_qty or 1.0
                line.excise_reduction_ratio = reduction_map.get(
                    product.excise_reduction, 1.0,
                )
            else:
                line.excise_weight = 0.0
                line.excise_volume = 0.0
                line.excise_pieces = 1.0
                line.excise_reduction_ratio = 1.0

    # ------------------------------------------------------------------
    # Display helpers for the "excise folded into the line price" mode.
    #
    # When the company flag ``excise_show_as_separate_row`` is OFF, the
    # QWeb inherits in ``views/report_templates.xml`` render
    # ``l10n_se_display_price_unit`` and
    # ``l10n_se_display_price_subtotal`` instead of the raw
    # ``price_unit`` / ``price_subtotal`` columns. The customer then
    # sees a self-consistent block where ``Unit Price × Quantity =
    # Amount`` and the sum of Amounts matches the bumped Untaxed
    # Amount in the totals block.
    #
    # Note: these fields are DISPLAY-only. The record's real
    # ``price_unit`` and ``price_subtotal`` stay at the net values
    # — that's what the tax engine and posting use. The excise tax
    # itself still runs through the engine and posts to its
    # liability account; only the customer-facing rendering is
    # adjusted.
    # ------------------------------------------------------------------
    excise_unit_amount = fields.Monetary(
        string="Excise (per unit)",
        compute='_compute_l10n_se_excise_display',
        help="Per-unit Swedish excise amount for this line, computed from "
             "the snapshot weight and reduction ratio. 0 when no excise "
             "tax is applied.",
    )
    l10n_se_display_price_unit = fields.Monetary(
        string="Unit Price (display)",
        compute='_compute_l10n_se_excise_display',
        help="Unit price shown on the customer-facing PDF and portal. "
             "Equals price_unit when excise is rendered on its own row; "
             "equals price_unit + per-unit excise when the company has "
             "folded the excise into the line price.",
    )
    l10n_se_display_price_subtotal = fields.Monetary(
        string="Amount (display)",
        compute='_compute_l10n_se_excise_display',
        help="Line Amount shown on the customer-facing PDF and portal. "
             "Equals price_subtotal when excise is rendered on its own "
             "row; equals price_subtotal + (qty × per-unit excise) when "
             "the company has folded the excise into the line price.",
    )

    @api.depends(
        'price_unit', 'price_subtotal', 'product_uom_qty',
        'tax_ids.amount_type', 'tax_ids.excise_type_id',
        'tax_ids.excise_type_id.unit_basis',
        'excise_weight', 'excise_volume', 'excise_pieces',
        'excise_reduction_ratio',
        'order_id.company_id.excise_show_as_separate_row',
        'order_id.company_id.country_id',
        'order_id.partner_id.l10n_se_approved_warehouse_keeper',
        'order_id.partner_id.country_id',
    )
    def _compute_l10n_se_excise_display(self):
        for line in self:
            excise_tax = line.tax_ids.filtered(
                lambda t: t.amount_type == 'swedish_excise'
            )[:1]
            per_unit = 0.0
            if excise_tax:
                # Skip the per-unit excise on exempt customers (AWK
                # or foreign) — same gate as the tax-engine hook in
                # _prepare_base_line_for_taxes_computation.
                partner = line.order_id.partner_id
                company = line.order_id.company_id
                exempt = bool(
                    partner
                    and company
                    and partner._l10n_se_is_excise_exempt(company)
                )
                if not exempt:
                    per_unit = excise_tax._get_excise_unit_amount(
                        weight=line.excise_weight or 0.0,
                        volume=line.excise_volume or 0.0,
                        pieces=line.excise_pieces or 0.0,
                        reduction_ratio=line.excise_reduction_ratio or 1.0,
                    )
            line.excise_unit_amount = per_unit
            fold = not (line.order_id.company_id.excise_show_as_separate_row
                        if line.order_id else True)
            if fold and per_unit:
                line_excise = (line.product_uom_qty or 0.0) * per_unit
                line.l10n_se_display_price_unit = line.price_unit + per_unit
                line.l10n_se_display_price_subtotal = (
                    line.price_subtotal + line_excise
                )
            else:
                line.l10n_se_display_price_unit = line.price_unit
                line.l10n_se_display_price_subtotal = line.price_subtotal

    # ------------------------------------------------------------------
    # Tax-engine integration
    # ------------------------------------------------------------------
    def _prepare_base_line_for_taxes_computation(self, **kwargs):
        """Inject the line-level excise snapshot into the base line
        dict and into the context of the taxes the engine will iterate,
        so ``account.tax._compute_amount`` can read the weight and
        reduction factor for this specific line.

        Also drops the swedish_excise tax from ``base_line['tax_ids']``
        when the order's customer is exempt (Approved Warehouse Keeper
        or based outside the company's country) — that way the tax
        engine never even sees the excise for them, no 0-kr tax row
        is generated, and the totals are computed cleanly as if the
        excise didn't apply at all. The line's stored ``tax_ids``
        are intentionally left alone — only the tax computation for
        this base_line is filtered.
        """
        base_line = super()._prepare_base_line_for_taxes_computation(**kwargs)
        excise_taxes = self.tax_ids.filtered(
            lambda t: t.amount_type == 'swedish_excise'
        )
        if not excise_taxes:
            return base_line

        partner = self.order_id.partner_id
        company = self.order_id.company_id
        if partner and partner._l10n_se_is_excise_exempt(company):
            if base_line.get('tax_ids'):
                base_line['tax_ids'] = base_line['tax_ids'].filtered(
                    lambda t: t.amount_type != 'swedish_excise'
                )
            return base_line

        excise_ctx = {
            'excise_line_vals': {
                'excise_weight': self.excise_weight or 0.0,
                'excise_volume': self.excise_volume or 0.0,
                'excise_pieces': self.excise_pieces or 1.0,
                'excise_reduction_ratio': self.excise_reduction_ratio or 1.0,
            },
        }
        # Propagate the snapshot to the tax recordset that the engine
        # will call _compute_amount on.
        if base_line.get('tax_ids'):
            base_line['tax_ids'] = base_line['tax_ids'].with_context(**excise_ctx)
        # Keep the raw values on the base line itself so other
        # hooks (reports, portal) can access them.
        base_line.update(excise_ctx['excise_line_vals'])
        return base_line

    # ------------------------------------------------------------------
    # Carry the snapshot onto the generated invoice line so downstream
    # invoicing uses the same excise basis as the confirmed order.
    # ------------------------------------------------------------------
    def _prepare_invoice_line(self, **optional_values):
        vals = super()._prepare_invoice_line(**optional_values)
        vals['excise_weight'] = self.excise_weight or 0.0
        vals['excise_volume'] = self.excise_volume or 0.0
        vals['excise_pieces'] = self.excise_pieces or 1.0
        vals['excise_reduction_ratio'] = self.excise_reduction_ratio or 1.0
        return vals
