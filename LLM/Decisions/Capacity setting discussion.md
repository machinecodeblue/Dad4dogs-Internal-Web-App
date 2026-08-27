# Decision

- **Status:** accepted (design rationale)
- **Live spec:** LLM/admin.md (daily capacity purpose + planned CapacitySettings move); storage design in LLM/Proposed work/Multi-tenant schema Option B.md section 4.3
- **What we took:** Split capacity into dedicated CapacitySettings; keep standard vs insurance semantics; keep orchestration in capacity.py; future expansion directions (staffing/weekday overrides, isolation buffer, service capacity_exempt)
- **What we left:** Do not implement weekday maps, weather modes, or weighted evaluation slots in Phase 1 — only migrate the two existing integers
- **Why:** Real-world capacity drivers will grow; two integers on BusinessProfile would become a god settings bag; Phase 1 stays behavior-preserving

---

---

### 1. Staffing Ratios & Daily Coverage Dynamics

* **Staff-to-Dog Ratios:** Capacity is fundamentally bounded by active supervisor bandwidth. A solo operator might comfortably handle 6–8 dogs, whereas adding a trained helper on peak drop-off days (e.g., Mondays and Fridays) can safely raise standard handling capacity.


* **Shift Hand-Offs & Solo Windows:** Early morning intake and late afternoon pick-up windows create operational friction. If extra help leaves at 3:00 PM, an operator is effectively solo for late-day yard management and feeding.

---

### 2. Behavioral Dynamics & Pack Energy

* **Temperament & Drive:** Ten low-energy senior dogs require significantly less supervision and spatial separation than four high-drive, reactive adolescents.
* **Trial & Evaluation Stays:** New dogs in the pipeline (e.g., Meet & Greet or Evaluation stays) demand dedicated 1-on-1 observation, effectively consuming the supervision bandwidth of two or three familiar, well-integrated regulars.


* **Pack Size Thresholds:** Group dynamic risks increase non-linearly with pack size. When a group exceeds a certain threshold, the risk of redirection, arousal spikes, or barrier frustration increases, requiring tighter capacity buffers.

---

### 3. Physical Space, Zoning & Weather Constraints

* **Indoor vs. Outdoor Usable Area:** Municipal bylaws, zoning constraints, and commercial insurance policies frequently mandate minimum square footage per dog.
* **Weather-Driven Capacity Drops:** Heavy rain, extreme heat, or freezing winter conditions force dogs indoors. If outdoor yard access is restricted, usable square footage shrinks immediately, lowering practical capacity.
* **Rest, Crate & Separation Capacity:** Dogs require structured decompression periods. Total daily capacity cannot exceed the number of safe, isolated resting zones, suites, or crates available for simultaneous feeding and rest.

---

### 4. Stay Types & Temporal Overlaps

* **Daycare vs. Overnight Boarding:** Overnight guests occupy yard space during daytime daycare hours. Daycare capacity must account for overnight dogs already on-site.


* **Peak Turnover Windows:** Midday overlaps—where morning daycare dogs are still on site while afternoon drop-ins or boarders arrive—temporarily push counts toward the insurance ceiling.


* **Drop-In & Non-Canine Services:** Services like house checks or property visits take the operator off-site, directly impacting on-site dog supervision bandwidth (unless designated as capacity-exempt).



---

### 5. Regulatory, Insurance & Health Compliance

* **Hard Policy Ceilings:** Commercial liability insurance policies establish strict, non-negotiable maximum coverage limits. Exceeding this ceiling—even during brief midday overlaps—creates substantial liability exposure.


* **Isolation / Quarantine Buffers:** Safe facilities maintain reserve capacity (at least one dedicated isolation space) to quarantine a dog exhibiting sudden illness, kennel cough symptoms, or GI distress without disrupting standard operations.

---

### Architectural Takeaway for `CapacitySettings`

These real-world factors reinforce why extracting capacity into a dedicated `CapacitySettings` model is the right design:

| Factor | How the Data Model Supports It |
| --- | --- |
| **Scheduled Staff Days** | Day-of-week override dictionaries (e.g., higher ceiling on Mon/Fri). |
| **Emergency Buffers** | Distinguishing soft comfortable capacity (`standard_capacity`) from the hard policy stop (`insurance_ceiling`).

 |
| **Non-Canine / Off-Site Care** | Service-level flags (`capacity_exempt = True`) to avoid blocking dog daycare quotas.

 |
