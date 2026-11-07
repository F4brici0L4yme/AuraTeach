ALTER TABLE "models" ADD COLUMN "catalog_key" text;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "asset_key" text;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "thumbnail_key" text;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "source" text;--> statement-breakpoint
ALTER TABLE "models" ADD COLUMN "license" text;--> statement-breakpoint
ALTER TABLE "models" ADD CONSTRAINT "models_catalog_key_unique" UNIQUE("catalog_key");