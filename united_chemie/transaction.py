import json
from collections import defaultdict

import frappe
from frappe import _, bold
from frappe.model import delete_doc
from frappe.utils import cint, flt
from erpnext.controllers.accounts_controller import get_taxes_and_charges

from india_compliance.gst_india.constants import (
    GST_TAX_TYPES,
    SALES_DOCTYPES,
    STATE_NUMBERS,
)
from india_compliance.gst_india.constants.custom_fields import E_WAYBILL_INV_FIELDS
from india_compliance.gst_india.doctype.gstin.gstin import (
    _validate_gst_transporter_id_info,
    _validate_gstin_info,
    get_gstin_status,
)
from india_compliance.gst_india.utils import (
    get_all_gst_accounts,
    get_gst_accounts_by_tax_type,
    get_gst_accounts_by_type,
    get_hsn_settings,
    get_place_of_supply,
    get_place_of_supply_options,
    is_overseas_doc,
    join_list_with_custom_separators,
    validate_gst_category,
    validate_gstin,
)
from india_compliance.income_tax_india.overrides.tax_withholding_category import (
    get_tax_withholding_accounts,
)
from india_compliance.gst_india.overrides.transaction import (validate_place_of_supply, ignore_gst_validations, validate_company_address_field, validate_mandatory_fields, 
validate_overseas_gst_category,validate_gst_accounts,update_taxable_values,set_reverse_charge_as_per_gst_settings,validate_ecommerce_gstin,validate_hsn_codes,validate_gst_transporter_id, validate_reverse_charge_transaction, validate_gstin_status)

DOCTYPES_WITH_GST_DETAIL = {
    "Supplier Quotation",
    "Purchase Order",
    "Purchase Receipt",
    "Quotation",
    "Sales Order",
    "Delivery Note",
    "Sales Invoice",
    "POS Invoice",
}

def validate_transaction_custom(doc, method=None):
    if ignore_gst_validations(doc):
        return False

    if doc.place_of_supply:
        validate_place_of_supply(doc)
    else:
        doc.place_of_supply = get_place_of_supply(doc, doc.doctype)

    if validate_company_address_field(doc) is False:
        return False

    if validate_mandatory_fields(doc, ("company_gstin", "place_of_supply")) is False:
        return False

    # Ignore validation for Quotation not to Customer
    if doc.doctype != "Quotation" or doc.quotation_to == "Customer":
        if (
            validate_mandatory_fields(
                doc,
                "gst_category",
                _(
                    "{0} is a mandatory field for GST Transactions. Please ensure that"
                    " it is set in the Party and / or Address."
                ),
            )
            is False
        ):
            return False

    elif not doc.gst_category:
        doc.gst_category = "Unregistered"

    validate_overseas_gst_category(doc)

    if is_sales_transaction := doc.doctype in SALES_DOCTYPES:
        validate_hsn_codes(doc)
        gstin = doc.billing_address_gstin
    elif doc.doctype == "Payment Entry":
        is_sales_transaction = True
        gstin = doc.billing_address_gstin
    else:
        validate_reverse_charge_transaction(doc)
        gstin = doc.supplier_gstin

    validate_gstin_status(gstin, doc.get("posting_date") or doc.get("transaction_date"))
    validate_gst_transporter_id(doc)
    validate_ecommerce_gstin(doc)

    validate_gst_category(doc.gst_category, gstin)

    set_reverse_charge_as_per_gst_settings(doc)

    valid_accounts = validate_gst_accounts(doc, is_sales_transaction) or ()
    update_taxable_values(doc, valid_accounts)
    validate_item_wise_tax_detail(doc, valid_accounts)

def validate_item_wise_tax_detail(doc, gst_accounts):
    if doc.doctype not in DOCTYPES_WITH_GST_DETAIL:
        return

    item_taxable_values = defaultdict(float)

    for row in doc.items:
        item_key = row.item_code or row.item_name
        item_taxable_values[item_key] += row.taxable_value

    for row in doc.taxes:
        if row.account_head not in gst_accounts:
            continue

        if row.charge_type != "Actual":
            continue

        item_wise_tax_detail = frappe.parse_json(row.item_wise_tax_detail or "{}")

        for item_name, (tax_rate, tax_amount) in item_wise_tax_detail.items():
            if tax_amount and not tax_rate:
                frappe.throw(
                    _(
                        "Tax Row #{0}: Charge Type is set to Actual. However, this would"
                        " not compute item taxes, and your further reporting will be affected."
                    ).format(row.idx),
                    title=_("Invalid Charge Type"),
                )

            # Sales Invoice is created with manual tax amount. So, when a sales return is created,
            # the tax amount is not recalculated, causing the issue.
            item_taxable_value = item_taxable_values.get(item_name, 0)
            tax_difference = abs(item_taxable_value * tax_rate / 100 - tax_amount)

            if tax_difference > 1:
                pass
                # frappe.throw(
                #     _(
                #         "Tax Row #{0}: Charge Type is set to Actual. However, Tax Amount {1} as computed for Item {2}"
                #         " is incorrect. Try setting the Charge Type to On Net Total."
                #     ).format(row.idx, tax_amount, bold(item_name))
                # )
