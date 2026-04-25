# -*- coding: utf-8 -*-
"""Lower the sequence of the shipped CHEM E / CHEM M excise taxes
from 1 to 0 on existing databases.

The standard Swedish 25 % VAT taxes ship at sequence=1. Earlier
versions of this module created CHEM E / CHEM M at sequence=1
too. Odoo's tax engine sorts taxes by ``(sequence, id)`` and the
VAT records have lower ids than ours (chart loaded first), so
the engine processed VAT *before* excise — which silently broke
the ``include_base_amount`` cascade and left VAT computed on the
bare subtotal rather than ``subtotal + excise``.

The data file at 19.0.1.3.1+ creates these records at
sequence=0; this script updates already-installed records.
``noupdate="1"`` on the data block prevents Odoo's standard
data-reload machinery from doing it for us, so we do it via SQL.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE account_tax
           SET sequence = 0
         WHERE id IN (
                SELECT res_id
                  FROM ir_model_data
                 WHERE module = 'l10n_se_excise_tax'
                   AND model = 'account.tax'
                   AND name IN (
                           'tax_chemical_electronics',
                           'tax_chemical_appliances'
                       )
               )
           AND sequence > 0
        """
    )
