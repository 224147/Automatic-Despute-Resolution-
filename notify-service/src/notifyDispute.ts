import { sendMail } from "./mail";

interface NotifyDisputePayload {
  customerId: string;
  customerName?: string;
  disputeId: string;
  responseText: string;
}

export async function notifyDisputeResponse({
  customerId,
  customerName,
  disputeId,
  responseText,
}: NotifyDisputePayload) {
  const NOTIFY_TO = process.env.NOTIFY_TO || "rohitraj776407@gmail.com";
  const FRONTEND_URL = process.env.FRONTEND_URL || "http://localhost:3000";
  const disputeLink = `${FRONTEND_URL}/?dispute_id=${disputeId}`;

  const html = `
    <div style="font-family: Arial, sans-serif; color: #222;">
      <h2>Dispute Update</h2>
      <p>Hi ${customerName || customerId},</p>
      <p>There's a new response on your dispute <strong>#${disputeId}</strong>:</p>
      <blockquote style="border-left: 3px solid #ccc; margin: 12px 0; padding: 8px 16px; background: #f9f9f9;">
        ${responseText}
      </blockquote>
      <p>
        <a href="${disputeLink}" style="display:inline-block;padding:10px 18px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;">
          View Dispute Status
        </a>
      </p>
      <p style="color:#888;font-size:12px;">Customer ID: ${customerId}</p>
    </div>
  `;

  await sendMail({
    to: NOTIFY_TO,
    subject: `Dispute #${disputeId} — New Response`,
    html,
  });
}
