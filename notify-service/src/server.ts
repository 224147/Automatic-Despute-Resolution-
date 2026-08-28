import express from "express";
import { notifyDisputeResponse } from "./notifyDispute";

const app = express();
app.use(express.json());

// Called when the customer clicks "Dispute" after seeing the response.
app.post("/api/notify-dispute", async (req, res) => {
  const { customerId, customerName, disputeId, responseText } = req.body || {};

  if (!customerId || !disputeId || !responseText) {
    return res.status(400).json({
      error: "customerId, disputeId and responseText are required",
    });
  }

  try {
    await notifyDisputeResponse({ customerId, customerName, disputeId, responseText });
    res.json({ success: true });
  } catch (err) {
    res.status(500).json({ error: "Failed to send notification email" });
  }
});

const PORT = process.env.NOTIFY_PORT || 4000;
app.listen(PORT, () => {
  console.log(`Notify service listening on port ${PORT}`);
});
