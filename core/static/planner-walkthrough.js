/* Small, non-modal guide: the planner stays usable throughout. */
window.LeavePrintsWalkthrough = class {
    constructor({ hasRoute, isEditing, track }) {
        this.hasRoute = hasRoute;
        this.track = track;
        this.key = "leaveprints.planner-walkthrough.v1";
        this.card = document.getElementById("plannerWalkthrough");
        this.replay = document.getElementById("replayWalkthrough");
        this.next = document.getElementById("walkthroughNext");
        this.skip = document.getElementById("walkthroughSkip");
        this.active = false;
        this.step = 0;
        this.target = null;
        this.replay.addEventListener("click", () => this.start(true));
        this.skip.addEventListener("click", () => this.finish(false));
        const search = document.getElementById("citySearch");
        // Make room for the keyboard and autocomplete while choosing a city.
        search.addEventListener("focus", () => {
            if (this.active && this.step === 0) this.card.hidden = true;
        });
        search.addEventListener("blur", () => requestAnimationFrame(() => {
            if (this.active && this.step === 0) {
                this.card.hidden = false;
                this.position();
            }
        }));
        this.next.addEventListener("click", () => {
            if (this.step === 1) this.show(2, true);
            else this.finish(true);
        });
        document.addEventListener("keydown", event => {
            if (this.active && event.key === "Escape") this.finish(false);
        });
        const reposition = () => {
            if (!this.active || this.frame) return;
            this.frame = requestAnimationFrame(() => {
                this.frame = null;
                this.position();
            });
        };
        window.addEventListener("resize", reposition);
        window.addEventListener("scroll", reposition, { passive: true });
        window.visualViewport?.addEventListener("resize", reposition);
        window.visualViewport?.addEventListener("scroll", reposition);
        let seen = false;
        try { seen = Boolean(localStorage.getItem(this.key)); } catch (_) {}
        // Existing, restored and shared routes already have a budget. Do not
        // interrupt those flows or automatically tour saved-trip editing.
        if (!seen && !isEditing && !hasRoute()) this.start(false);
    }

    start(manual) {
        this.active = true;
        this.manual = manual;
        try { localStorage.setItem(this.key, "seen"); } catch (_) {}
        this.track("walkthrough_started");
        this.show(this.hasRoute() ? 1 : 0, true);
    }

    clearTarget() {
        if (!this.target) return;
        this.target.classList.remove("walkthrough-target");
        const descriptions = (this.described.getAttribute("aria-describedby") || "")
            .split(" ").filter(id => id && id !== "walkthroughCopy");
        if (descriptions.length) this.described.setAttribute("aria-describedby", descriptions.join(" "));
        else this.described.removeAttribute("aria-describedby");
        this.target = null;
    }

    show(step, scroll) {
        this.clearTarget();
        this.step = step;
        const steps = [
            ["Where do you want to go?", "Type a city in the highlighted search box, then choose it from the results. Not sure yet? Try Budapest below.", "walkthrough_destination_seen"],
            ["How long are you staying?", "Set the nights for your first stop with the + and − buttons, or type a number. Your estimate updates as you go.", "walkthrough_nights_seen"],
            ["Here's your trip budget", "This estimate includes accommodation and living costs. Add transport costs when you know them. Add another destination, or choose Keep my trip to save and revisit it.", "walkthrough_budget_seen"]
        ];
        const [title, copy, event] = steps[step];
        document.getElementById("walkthroughStep").textContent = `Quick tour · ${step + 1} of 3`;
        document.getElementById("walkthroughTitle").textContent = title;
        document.getElementById("walkthroughCopy").textContent = copy;
        this.next.hidden = step === 0;
        this.next.textContent = step === 1 ? "Use these nights →" : "Got it";
        this.skip.textContent = step === 2 ? "Close tour" : "Skip tour";
        this.target = step === 0 ? document.getElementById("citySearch")
            : step === 1 ? document.querySelector(".route-stop .nights-control")
            : document.getElementById("tripTotal").closest(".summary-total");
        if (!this.target) { this.finish(false); return; }
        this.target.classList.add("walkthrough-target");
        this.described = this.target.querySelector("input") || this.target;
        const description = this.described.getAttribute("aria-describedby");
        this.described.setAttribute("aria-describedby", [description, "walkthroughCopy"].filter(Boolean).join(" "));
        this.card.hidden = false;
        this.track(event);
        if (scroll) {
            this.target.scrollIntoView({ behavior: "instant", block: "center" });
            const rect = this.target.getBoundingClientRect();
            const navBottom = document.querySelector(".site-nav")?.getBoundingClientRect().bottom || 0;
            const targetTop = Math.max(12, navBottom + 12) + this.card.offsetHeight + 14;
            if (rect.top < targetTop && targetTop + rect.height < window.innerHeight - 12) {
                window.scrollBy({ top: rect.top - targetTop, behavior: "instant" });
            }
        }
        this.position();
        // Automatic guidance never steals focus. Keyboard users can replay
        // the tour and reach its action buttons without hunting around.
        if (this.manual && scroll) (step === 0 ? this.skip : this.next).focus({ preventScroll: true });
    }

    position() {
        if (!this.active || this.card.hidden || !this.target?.isConnected) return;
        const rect = this.target.getBoundingClientRect();
        const viewport = window.visualViewport;
        const top = viewport?.offsetTop || 0;
        const height = viewport?.height || window.innerHeight;
        const width = viewport?.width || window.innerWidth;
        const cardHeight = this.card.offsetHeight;
        const cardWidth = this.card.offsetWidth;
        const gap = 14;
        const above = rect.top - cardHeight - gap >= top + 12;
        const desired = above ? rect.top - cardHeight - gap : rect.bottom + gap;
        const y = Math.max(top + 12, Math.min(desired, top + height - cardHeight - 12));
        const x = Math.max(12, Math.min(rect.left, width - cardWidth - 12));
        this.card.style.left = `${x}px`;
        this.card.style.top = `${y}px`;
        this.card.dataset.placement = above ? "above" : "below";
        this.card.style.setProperty("--walkthrough-arrow", `${Math.max(20, Math.min(cardWidth - 30, rect.left + rect.width / 2 - x))}px`);
    }

    sync() {
        if (!this.active) return;
        if (!this.hasRoute()) this.show(0, false);
        else if (this.step === 0) this.show(1, true);
        else this.show(this.step, false); // Rebind after route rows rerender.
    }

    nightsChosen() {
        if (this.active && this.step === 1) this.show(2, true);
    }

    finish(completed) {
        const focusWasInCard = this.card.contains(document.activeElement);
        const focusTarget = this.step === 2 ? document.querySelector(".budget-ready-save")
            : this.target?.querySelector("input") || this.target;
        this.active = false;
        this.card.hidden = true;
        this.clearTarget();
        this.track(completed ? "walkthrough_completed" : "walkthrough_skipped");
        if (focusWasInCard) {
            const destination = focusTarget?.isConnected && !focusTarget.disabled ? focusTarget : this.replay;
            destination.focus({ preventScroll: true });
        }
    }
};
