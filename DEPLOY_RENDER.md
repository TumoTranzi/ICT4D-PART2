# Free Render demo deployment

This configuration deploys TTsebisa on Render's free web-service plan. It does not require paid compute or a persistent disk, and it does not change the existing PythonAnywhere app.

## Free-plan limits to understand

- Render may spin a free service down after 15 minutes without traffic; the next visit can take about a minute to wake.
- This app uses SQLite and stores uploads on the service filesystem. On the free plan, local SQLite data, photos and voice notes can be lost when Render restarts, spins down or redeploys the service.
- Use this for a three-week demonstration with test data only. Download anything you need to keep before a redeploy or restart. Do not collect real citizen case data on this temporary setup.
- This deployment gives the website and browser USSD simulator a public URL. It does not provide a carrier short code or outbound SMS.

Render documents these limits in its [free-plan guide](https://render.com/docs/free).

## Deploy

1. Keep this project in the private GitHub repository `TumoTranzi/ICT4D-PART2` on branch `main`.
2. In Render, select **New → Blueprint** and connect that repository. The Blueprint file is `render.yaml` at the repository root.
3. Provide a unique value for `TSEBISA_ADMIN_PASSWORD`. Render generates `TSEBISA_SECRET_KEY`.
4. Confirm the web service plan is **Free**, and do not add a disk or select a paid plan.
5. Deploy. Open the `onrender.com` URL on the service page. The simulator is at `/ussd-simulator`; staff sign in at `/login` with username `admin` and the password entered during setup.

If Render still asks for payment details, cancel that flow. Confirm the latest commit on GitHub includes `plan: free` in `render.yaml`, then create or sync the Blueprint again.
