"""Deployment adapters. Publishing is APPROVED -> PUBLISHED (a local status change) and, separately,
an adapter that gets the built site onto a host. Only the manual adapter is implemented; the others
are placeholders so the hosting choice can change without touching the pipeline.

Nothing here runs unless the operator calls scripts/publish_article.py, and no adapter deploys
unless config/publishing.yaml -> deployment.auto_deploy is true.
"""
from __future__ import annotations


class DeployAdapter:
    name = "base"

    def deploy(self, site_dir, changed: list[str]) -> str:
        raise NotImplementedError


class ManualAdapter(DeployAdapter):
    """No network access, no credentials. Tells the operator what to do by hand."""
    name = "manual"

    def deploy(self, site_dir, changed: list[str]) -> str:
        return ("Manual deployment: nothing was pushed. To put this live, build with `npm run build` in "
                f"{site_dir} and upload the `dist/` folder to your host, or commit and push if the host "
                "builds from git.")


class _NotConfigured(DeployAdapter):
    def deploy(self, site_dir, changed: list[str]) -> str:
        raise NotImplementedError(
            f"The {self.name} adapter is a placeholder. It needs credentials and an explicit go-ahead "
            "from the operator before it is implemented.")


class VercelAdapter(_NotConfigured):
    name = "vercel"


class NetlifyAdapter(_NotConfigured):
    name = "netlify"


class CloudflarePagesAdapter(_NotConfigured):
    name = "cloudflare_pages"


ADAPTERS = {a.name: a for a in (ManualAdapter, VercelAdapter, NetlifyAdapter, CloudflarePagesAdapter)}


def get_adapter(cfg: dict) -> DeployAdapter:
    return ADAPTERS[cfg["publishing"]["deployment"]["adapter"]]()


def deploy_if_enabled(cfg: dict, site_dir, changed: list[str]) -> str:
    if not cfg["publishing"]["deployment"]["auto_deploy"]:
        return ("Automatic deployment is off (config/publishing.yaml -> deployment.auto_deploy). "
                + ManualAdapter().deploy(site_dir, changed))
    return get_adapter(cfg).deploy(site_dir, changed)
