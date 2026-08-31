"""The payment-provider adapter.

Its whole job is translation at the boundary: a `RazorpayError` carrying HTTP 404 becomes
`GatewayArtifactNotFound`, anything else from the provider becomes `GatewayError`, and any
other exception is left alone so the pipeline's safety net still sees it as the unexpected
error it is.

That translation is the point. Before it, `tasks.py` asked
`razorpay_client.is_not_found(err)` — an HTTP status code read from inside a business
decision about whether a payable artifact can be re-issued. Now the execution logic branches
on a domain type and stays correct if the provider's status vocabulary ever changes.

Every call resolves `razorpay_client.<fn>` at call time rather than binding the function at
import. That is not incidental: several tests patch those module attributes, and a bound
reference would make the patch invisible.
"""

from .. import razorpay_client
from ..exceptions import GatewayArtifactNotFound, GatewayError
from ..interfaces.ports import PaymentGatewayInterface


class RazorpayGateway(PaymentGatewayInterface):
    @staticmethod
    def _translate(fn_name, *args, **kwargs):
        fn = getattr(razorpay_client, fn_name)
        try:
            return fn(*args, **kwargs)
        except razorpay_client.RazorpayError as err:
            if razorpay_client.is_not_found(err):
                raise GatewayArtifactNotFound(str(err), cause=err) from err
            raise GatewayError(str(err), cause=err) from err

    def reopen_order_checkout(self, order_id, amount_paise, receipt, customer_name, customer_phone):
        return self._translate(
            "reopen_order_checkout", order_id, amount_paise, receipt, customer_name, customer_phone
        )

    def create_payment_link(self, amount_paise, description, customer_name, customer_phone):
        return self._translate("create_payment_link", amount_paise, description,
                               customer_name, customer_phone)

    def create_registration_link(self, amount_paise, description, customer_name, customer_phone):
        return self._translate("create_registration_link", amount_paise, description,
                               customer_name, customer_phone)

    def resend_invoice(self, invoice_id, medium="sms"):
        return self._translate("resend_invoice", invoice_id, medium=medium)
