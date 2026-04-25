# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    """Partner-level fields and helpers that govern whether the
    Swedish chemical excise tax (Kemikalieskatt) applies on lines
    billed to / sold to this partner.
    """

    _inherit = 'res.partner'

    l10n_se_approved_warehouse_keeper = fields.Boolean(
        string="Approved Warehouse Keeper",
        help="Mark this partner as an Approved Warehouse Keeper "
             "(Swedish: 'Godkänd lagerhållare') — a company "
             "registered with Skatteverket to handle excise goods "
             "under deferred duty. When this is enabled, the "
             "Swedish chemical excise tax is NOT computed on "
             "quotations or invoices issued to this partner. The "
             "AWK is responsible for declaring and paying the tax "
             "themselves when they sell the goods on to a non-AWK "
             "end customer.",
    )

    def _l10n_se_is_excise_exempt(self, company):
        """Return True when the Swedish chemical excise tax should
        NOT be computed on lines billed to this partner from the
        given ``company``.

        Two reasons exempt a partner:

        1. **Approved Warehouse Keeper.** The partner is registered
           with Skatteverket as an AWK and handles the tax under
           the deferred-duty regime themselves. Driven by the
           ``l10n_se_approved_warehouse_keeper`` flag on the partner.
        2. **Foreign customer.** The partner's country is set and
           differs from the company's country. Swedish chemical
           tax is a domestic tax — exports do not carry it. If
           either side has no ``country_id`` set we conservatively
           return False (don't exempt) and leave the tax in place.

        :param company: ``res.company`` record whose country we
            compare against.
        :return: True when the excise should be skipped.
        """
        self.ensure_one()
        if self.l10n_se_approved_warehouse_keeper:
            return True
        if (self.country_id
                and company
                and company.country_id
                and self.country_id != company.country_id):
            return True
        return False
