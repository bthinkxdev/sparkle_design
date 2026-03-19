import logging
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Banner, Category, Order, Payment, VariantImage

logger = logging.getLogger(__name__)


def _delete_image_file(image_field):
    """
    Safely delete an image file using its storage backend.
    Works with both local filesystem and S3/cloud storage.
    Skips storage.exists() check because S3 eventual consistency
    can cause it to return False for recently-created files.
    S3 delete_object is idempotent so calling delete() on a
    non-existent key is safe.
    """
    if not image_field or not image_field.name:
        return
    try:
        storage = image_field.storage
        name = image_field.name
        logger.info(f"Deleting old image from storage: {name}")
        storage.delete(name)
    except Exception as e:
        logger.warning(f"Failed to delete image file '{image_field.name}': {e}")


# ── Category signals ──

@receiver(post_delete, sender=Category)
def delete_category_image_file(sender, instance, **kwargs):
    """Delete image file when Category instance is deleted."""
    _delete_image_file(instance.image)


@receiver(pre_save, sender=Category)
def delete_old_category_image_on_update(sender, instance, **kwargs):
    """Delete old image file when Category is updated with a new image."""
    if not instance.pk:
        return
    try:
        old_image = Category.objects.get(pk=instance.pk).image
    except Category.DoesNotExist:
        return
    if old_image and old_image != instance.image:
        _delete_image_file(old_image)


# ── VariantImage signals ──

@receiver(post_delete, sender=VariantImage)
def delete_variant_image_file(sender, instance, **kwargs):
    """Delete image file when a VariantImage is deleted."""
    _delete_image_file(instance.image)


@receiver(pre_save, sender=VariantImage)
def delete_old_variant_image_on_update(sender, instance, **kwargs):
    """Delete old image file when a variant image is replaced."""
    if not instance.pk:
        return
    try:
        old_image = VariantImage.objects.get(pk=instance.pk).image
    except VariantImage.DoesNotExist:
        return
    if old_image and old_image != instance.image:
        _delete_image_file(old_image)


# ── Banner signals ──

@receiver(post_delete, sender=Banner)
def delete_banner_image_file(sender, instance, **kwargs):
    """Delete image file when a Banner is deleted."""
    _delete_image_file(instance.image)


@receiver(pre_save, sender=Banner)
def delete_old_banner_image_on_update(sender, instance, **kwargs):
    """Delete old image file from storage when a banner image is replaced."""
    if not instance.pk:
        return
    try:
        old_image = Banner.objects.get(pk=instance.pk).image
    except Banner.DoesNotExist:
        return
    if old_image and old_image != instance.image:
        _delete_image_file(old_image)


# ── Order signals ──

@receiver(post_save, sender=Order)
def auto_mark_cod_payment_paid_on_delivery(sender, instance, created, update_fields=None, **kwargs):
    """Auto-mark COD payment as PAID when order is delivered."""
    if created:
        return
    if instance.status != Order.Status.DELIVERED:
        return
    if update_fields is not None and "status" not in update_fields:
        return
    try:
        payment = instance.payment
        if payment.method == Payment.Method.COD and payment.status != Payment.Status.PAID:
            payment.status = Payment.Status.PAID
            payment.processed_at = timezone.now()
            payment.save(update_fields=["status", "processed_at"])
    except Payment.DoesNotExist:
        pass
    except Exception as exc:
        logger.error(
            "auto_mark_cod_payment_paid_on_delivery failed for order %s: %s",
            getattr(instance, "order_number", None),
            exc,
            exc_info=True,
        )