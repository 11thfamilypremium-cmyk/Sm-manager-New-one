import io
import base64
import qrcode
from urllib.parse import quote
from config import Config

class UPIService:
    @staticmethod
    def generate_upi_uri(amount: float, note: str = "VIP Access"):
        upi_id = Config.UPI_ID
        payee_name = Config.PAYEE_NAME
        # Format amount to 2 decimal places
        amount_str = f"{float(amount):.2f}"
        encoded_name = quote(payee_name)
        encoded_note = quote(note)
        
        uri = f"upi://pay?pa={upi_id}&pn={encoded_name}&am={amount_str}&cu=INR&tn={encoded_note}"
        return uri

    @staticmethod
    def generate_qr_base64(amount: float, note: str = "VIP Access"):
        uri = UPIService.generate_upi_uri(amount, note)
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        
        img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
        return f"data:image/png;base64,{img_str}"

    @staticmethod
    def generate_qr_bytes(amount: float, note: str = "VIP Access"):
        uri = UPIService.generate_upi_uri(amount, note)
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        return buffered.getvalue()
