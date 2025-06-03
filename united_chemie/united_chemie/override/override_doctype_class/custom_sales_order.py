from erpnext.controllers.accounts_controller import AccountsController
import frappe

class CustomSalesOrder(AccountsController):
    def validate_party_address(self, party, party_type, billing_address, shipping_address=None):
        if billing_address or shipping_address:
            party_address = frappe.get_all(
                "Dynamic Link",
                {"link_doctype": party_type, "link_name": party, "parenttype": "Address"},
                pluck="parent",
            )
            # if billing_address and billing_address not in party_address:
            #     frappe.throw(_("Billing Address does not belong to the {0}").format(party))
            # elif shipping_address and shipping_address not in party_address:
            #     frappe.throw(_("Shipping Address does not belong to the {0}").format(party))

    def validate(self):
        self.validate_party_address()
        super().validate()
