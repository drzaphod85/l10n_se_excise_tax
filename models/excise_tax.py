# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ExciseTaxType(models.Model):
    """A reusable description of "how this excise tax is computed":
    the per-unit rate, the optional cap, and — as of 19.0.2.0.0 —
    the *unit* the rate is expressed in (kg, litres, …) and the
    country whose excise system this type belongs to.

    The combination of ``unit_basis`` and ``tax_rate`` is what the
    engine hook in ``account_tax._eval_tax_amount_fixed_amount``
    reads to compute the excise. Different excise tax records can
    point at the same type (cf. CHEM E vs CHEM M sharing the same
    "Electronics (High Rate)" / "Major Appliances (Low Rate)"
    structure but with different reporting tags / posting accounts).
    """

    _name = 'excise.tax.type'
    _description = 'Excise Tax Type'

    name = fields.Char(
        string="Name",
        required=True,
        translate=True,
    )
    country_id = fields.Many2one(
        'res.country',
        string="Country",
        help="Excise regime this type belongs to. The shipped types "
             "are all Sweden; the field is here so future contributors "
             "can add Finland/Denmark/etc. excise rows without forking "
             "the model.",
        default=lambda self: self.env.ref('base.se', raise_if_not_found=False),
    )
    unit_basis = fields.Selection(
        selection=[
            ('kg', 'Weight in kilograms (kg)'),
            ('liter', 'Volume in litres (L)'),
            ('pcs', 'Piece count (per styck)'),
            # Future: 'tonne', 'liter_pure', 'm3', 'kWh',
            # 'passenger', 'percent_base'. Each one needs its own
            # branch in ``_eval_tax_amount_fixed_amount`` and a
            # matching per-product driver field, so they're added
            # alongside the relevant Phase-2/3/4 tax data.
        ],
        string="Unit Basis",
        default='kg',
        required=True,
        help="Decides which per-product field the tax-engine hook "
             "reads when computing the excise on a line, and what "
             "unit ``Tax Rate`` is expressed in. ``kg`` reads "
             "``net_weight_excise``; ``liter`` reads "
             "``excise_volume_litres``; ``pcs`` reads "
             "``excise_pieces_per_qty`` (per piece — useful for "
             "cigarettes / cigars where a pack of 20 = "
             "pieces_per_qty=20).",
    )
    tax_rate = fields.Float(
        string="Tax Rate",
        digits=(12, 2),
        help="Rate per ``unit_basis`` unit, in SEK (or the country's "
             "currency). E.g. 180.71 SEK per kg for high-rate "
             "Kemikalieskatt; 2020 SEK per litre for regular "
             "nicotine e-liquid.",
    )
    max_limit = fields.Float(
        string="Maximum Limit per Unit",
        digits=(12, 2),
        help="Optional per-unit cap on the computed excise amount "
             "(used by Kemikalieskatt only). 0 = no cap.",
    )
    has_reduction_levels = fields.Boolean(
        string="Has Per-Product Reductions",
        default=False,
        help="When enabled, products taxed with this excise type can "
             "select a reduction level (No / 50% / 90%). Specific to "
             "Kemikalieskatt — products with certain "
             "flame-retardant chemistries qualify for a 50% or 90% "
             "tax reduction. Other excise regimes (Nikotinskatt, "
             "alcohol, gravel, …) don't have this kind of "
             "per-product reduction; leave this off and the "
             "Reduction Level field is hidden on the product form "
             "and the reduction_ratio is ignored by the engine.",
    )


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_excise_taxable = fields.Boolean(string="Excise Taxable")

    excise_tax_type_id = fields.Many2one(
        'excise.tax.type',
        string="Excise Tax Type",
    )

    # ------------------------------------------------------------------
    # Per-unit-basis driver fields. Only the field matching the linked
    # excise type's ``unit_basis`` is read at line creation time and
    # snapshotted onto the order/invoice line. The other fields stay
    # at zero and don't influence anything.
    # ------------------------------------------------------------------
    net_weight_excise = fields.Float(
        string="Excise Tax Weight (kg)",
        help="Weight in kg used for excise tax calculation when the "
             "linked Excise Type's Unit Basis is 'kg' (e.g. "
             "Kemikalieskatt, nicotine pouches).",
    )
    excise_volume_litres = fields.Float(
        string="Excise Tax Volume (L)",
        help="Volume in litres used for excise tax calculation when "
             "the linked Excise Type's Unit Basis is 'liter' (e.g. "
             "nicotine e-liquid).",
    )
    excise_pieces_per_qty = fields.Float(
        string="Excise Pieces per Unit",
        default=1.0,
        digits=(12, 2),
        help="Number of countable pieces in one product unit, used "
             "for excise tax calculation when the linked Excise "
             "Type's Unit Basis is 'pcs'. Examples: a pack of 20 "
             "cigarettes sold as one product unit → 20; a single "
             "cigar → 1; a box of 10 cigars sold as one unit → 10.",
    )

    excise_reduction = fields.Selection(
        [
            ('0', 'No Reduction (100%)'),
            ('50', '50% Reduction'),
            ('95', '95% Reduction'),
        ],
        string="Reduction Level",
        default='0',
        help="Per-product reduction applied AFTER the per-unit cap. "
             "Specific to Kemikalieskatt rules: per Lag (2016:1067) "
             "and Skatteverket guidance, products earn:\n"
             "  - 50% reduction if they contain no bromine or "
             "    chlorine compounds (>0.1 wt% of the homogeneous "
             "    plastic / circuit-board material).\n"
             "  - 95% reduction if they contain none of bromine, "
             "    chlorine, OR phosphorus compounds.\n"
             "For other excise regimes (nicotine, tobacco, alcohol, "
             "…) leave this at 'No Reduction'.",
    )

    # ------------------------------------------------------------------
    # Per-unit excise amount, computed from the linked excise type
    # and the per-product driver fields. Used by the eCommerce
    # product-page price override (so the displayed price can include
    # the excise when the company is in "fold" mode), by the cart
    # line override, and by anywhere else that needs a no-line-yet
    # excise figure (e.g. catalog filters in the future).
    # ------------------------------------------------------------------
    excise_amount_per_unit = fields.Monetary(
        compute='_compute_excise_amount_per_unit',
        string="Excise Tax per Unit",
        currency_field='currency_id',
        help="Per-unit Swedish excise amount (kr) for this product, "
             "computed from the linked Excise Type's rate / cap / "
             "unit_basis and the matching driver field on the "
             "product (weight, volume or pieces). Reflects the "
             "Reduction Level if the linked type uses Kemikalieskatt-"
             "style reductions. 0 when the product is not excise-"
             "taxable or has no swedish_excise tax in its Customer "
             "Taxes.",
    )

    @api.depends(
        'is_excise_taxable',
        'taxes_id',
        'taxes_id.amount_type',
        'taxes_id.excise_type_id',
        'taxes_id.excise_type_id.unit_basis',
        'taxes_id.excise_type_id.tax_rate',
        'taxes_id.excise_type_id.max_limit',
        'taxes_id.excise_type_id.has_reduction_levels',
        'net_weight_excise',
        'excise_volume_litres',
        'excise_pieces_per_qty',
        'excise_reduction',
    )
    def _compute_excise_amount_per_unit(self):
        """Compute the per-unit excise amount for the product, from
        the linked swedish_excise tax in its Customer Taxes.

        Mirrors the engine hook's dispatch on ``unit_basis`` so the
        product-level value matches what the engine will compute for
        a sale-order or invoice line carrying this product.
        """
        reduction_map = {'0': 1.0, '50': 0.5, '95': 0.05}
        for product in self:
            amount = 0.0
            if product.is_excise_taxable:
                excise_tax = product.taxes_id.filtered(
                    lambda t: t.amount_type == 'swedish_excise'
                )[:1]
                if excise_tax:
                    amount = excise_tax._get_excise_unit_amount(
                        weight=product.net_weight_excise or 0.0,
                        volume=product.excise_volume_litres or 0.0,
                        pieces=product.excise_pieces_per_qty or 1.0,
                        reduction_ratio=reduction_map.get(
                            product.excise_reduction, 1.0,
                        ),
                    )
            product.excise_amount_per_unit = amount

    def _get_excise_inclusive_price(self, base_price):
        """Return ``base_price + excise_amount_per_unit`` when the
        company is in fold mode (``excise_show_as_separate_row`` is
        False), else return ``base_price`` unchanged.

        Used by the eCommerce product-page price template and the
        cart-line price override to keep the customer-facing display
        consistent with the totals breakdown — when fold is on, the
        cart's Subtotal shows the bumped value, so the per-line
        prices (and the product-detail price) should match.
        """
        self.ensure_one()
        company = self.env.company
        if not self.is_excise_taxable or company.excise_show_as_separate_row:
            return base_price
        return base_price + (self.excise_amount_per_unit or 0.0)

    # Mirror of the linked Excise Type's ``unit_basis``. Used by the
    # product form to switch which driver field is visible (kg vs
    # liter). Exposed as a related field so the view can reference
    # it directly with `invisible="excise_unit_basis == 'liter'"`,
    # which works reliably across Odoo 17/18/19 — putting the same
    # condition on `excise_tax_type_id.unit_basis` only sometimes
    # evaluates correctly because Odoo doesn't always pre-fetch
    # nested M2O fields into the form's record.
    excise_unit_basis = fields.Selection(
        related='excise_tax_type_id.unit_basis',
        string="Excise Unit Basis",
        readonly=True,
    )
    excise_has_reduction_levels = fields.Boolean(
        related='excise_tax_type_id.has_reduction_levels',
        string="Excise Has Reductions",
        readonly=True,
    )

    # ------------------------------------------------------------------
    # Default-rule integration. The actual rule lookup lives in
    # ``excise.tax.default._find_for_product``; this method applies a
    # matched rule to the product. It's invoked from:
    #
    #   * the Excise Taxable / category onchanges below — so a fresh
    #     product picks up the right defaults the moment the user
    #     ticks "Excise Taxable" or sets / changes the Internal
    #     Category;
    #   * the ``action_apply_excise_defaults`` server action — for
    #     bulk back-applying rules to products that pre-date the rule
    #     (or whose category was changed before the rule was added).
    #
    # The applier is conservative: it never overwrites an excise type
    # the user has already configured on the product, and it never
    # removes or replaces existing taxes in ``taxes_id``. It only
    # adds the rule's tax if no swedish_excise tax is already linked.
    # That keeps "Apply Defaults" idempotent and safe to run over a
    # large selection of products.
    # ------------------------------------------------------------------
    def _apply_excise_default(self, force=False):
        """Apply the matching ``excise.tax.default`` rule to ``self``.

        :param bool force:
            When False (the default), the method skips products that
            already have an ``excise_tax_type_id`` set or already
            carry a ``swedish_excise`` tax in ``taxes_id`` — those
            are considered configured by the user and left alone.

            When True, the rule's values overwrite the product's
            current excise type / reduction and the rule's tax is
            added if not already present (existing excise taxes are
            still NOT removed — bulk-applying defaults is meant to
            be additive, not destructive).

        Returns the recordset of products that were actually modified
        (handy for the server action's success notification).
        """
        Default = self.env['excise.tax.default']
        modified = self.browse()
        for product in self:
            rule = Default._find_for_product(product)
            if not rule:
                continue

            already_typed = bool(product.excise_tax_type_id)
            already_taxed = bool(product.taxes_id.filtered(
                lambda t: t.amount_type == 'swedish_excise'
            ))
            if not force and (already_typed or already_taxed):
                continue

            vals = {'is_excise_taxable': True}
            if force or not already_typed:
                vals['excise_tax_type_id'] = rule.excise_tax_type_id.id
            # Reduction is only meaningful when the linked type
            # supports it. ``excise_reduction`` defaults to '0' on
            # rules that don't, so writing it is harmless either
            # way, but skipping it keeps the audit trail tidy on
            # types without reductions.
            if rule.excise_has_reduction_levels:
                if force or not product.excise_reduction \
                        or product.excise_reduction == '0':
                    vals['excise_reduction'] = rule.excise_reduction or '0'
            product.write(vals)

            if rule.excise_tax_id and rule.excise_tax_id not in product.taxes_id:
                product.taxes_id = [(4, rule.excise_tax_id.id)]

            modified |= product
        return modified

    @api.onchange('is_excise_taxable', 'categ_id')
    def _onchange_apply_excise_default(self):
        """Suggest defaults when the user ticks Excise Taxable or
        changes the Internal Category and the product hasn't been
        configured for excise yet.

        Onchange-only (no DB write) — the user can still edit the
        suggestion before saving. Skipping when the user has already
        chosen an excise type avoids surprising overwrites.
        """
        for product in self:
            if not product.is_excise_taxable:
                continue
            if product.excise_tax_type_id:
                continue
            rule = self.env['excise.tax.default']._find_for_product(product)
            if not rule:
                continue
            product.excise_tax_type_id = rule.excise_tax_type_id
            if rule.excise_has_reduction_levels:
                product.excise_reduction = rule.excise_reduction or '0'
            if rule.excise_tax_id \
                    and rule.excise_tax_id not in product.taxes_id:
                product.taxes_id = [(4, rule.excise_tax_id.id)]

    def action_apply_excise_defaults(self):
        """Server action — bulk-apply default rules to a selection.

        Designed to be wired up as an
        ``ir.actions.server`` (model_id = product.template,
        binding_model_id = product.template, state = code,
        code = ``records.action_apply_excise_defaults()``).

        Conservative by default (``force=False``): products already
        configured for excise are left alone, so the action can be
        run repeatedly and over large selections without disrupting
        manual overrides.
        """
        modified = self._apply_excise_default(force=False)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Excise Defaults Applied"),
                'message': _(
                    "%(applied)s of %(total)s product(s) updated. "
                    "Products already configured for excise were "
                    "left unchanged."
                ) % {
                    'applied': len(modified),
                    'total': len(self),
                },
                'type': 'success',
                'sticky': False,
            },
        }
