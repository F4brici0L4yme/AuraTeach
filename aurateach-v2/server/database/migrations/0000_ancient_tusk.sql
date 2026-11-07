CREATE TABLE "classrooms" (
	"id" bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY (sequence name "classrooms_id_seq" INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1),
	"teacher_id" bigint NOT NULL,
	"name" text NOT NULL,
	"demo_key" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "classrooms_demo_key_unique" UNIQUE("demo_key")
);
--> statement-breakpoint
CREATE TABLE "enrollments" (
	"classroom_id" bigint NOT NULL,
	"student_id" bigint NOT NULL,
	CONSTRAINT "enrollments_pk" PRIMARY KEY("classroom_id","student_id")
);
--> statement-breakpoint
CREATE TABLE "model_visits" (
	"id" bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY (sequence name "model_visits_id_seq" INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1),
	"user_id" bigint NOT NULL,
	"model_id" bigint NOT NULL,
	"demo_key" text,
	"visited_at" timestamp with time zone NOT NULL,
	CONSTRAINT "model_visits_demo_key_unique" UNIQUE("demo_key")
);
--> statement-breakpoint
CREATE TABLE "models" (
	"id" bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY (sequence name "models_id_seq" INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1),
	"title" text NOT NULL,
	"topic" text NOT NULL,
	"demo_key" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "models_demo_key_unique" UNIQUE("demo_key")
);
--> statement-breakpoint
CREATE TABLE "student_questions" (
	"id" bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY (sequence name "student_questions_id_seq" INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1),
	"user_id" bigint NOT NULL,
	"model_id" bigint NOT NULL,
	"question_text" text NOT NULL,
	"demo_key" text,
	"asked_at" timestamp with time zone NOT NULL,
	CONSTRAINT "student_questions_demo_key_unique" UNIQUE("demo_key")
);
--> statement-breakpoint
CREATE TABLE "users" (
	"id" bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY (sequence name "users_id_seq" INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1),
	"role" text NOT NULL,
	"display_name" text NOT NULL,
	"demo_key" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "users_demo_key_unique" UNIQUE("demo_key"),
	CONSTRAINT "users_role_check" CHECK ("users"."role" in ('teacher', 'student'))
);
--> statement-breakpoint
ALTER TABLE "classrooms" ADD CONSTRAINT "classrooms_teacher_id_fk" FOREIGN KEY ("teacher_id") REFERENCES "public"."users"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "enrollments" ADD CONSTRAINT "enrollments_classroom_id_fk" FOREIGN KEY ("classroom_id") REFERENCES "public"."classrooms"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "enrollments" ADD CONSTRAINT "enrollments_student_id_fk" FOREIGN KEY ("student_id") REFERENCES "public"."users"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "model_visits" ADD CONSTRAINT "model_visits_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "model_visits" ADD CONSTRAINT "model_visits_model_id_fk" FOREIGN KEY ("model_id") REFERENCES "public"."models"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "student_questions" ADD CONSTRAINT "student_questions_user_id_fk" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "student_questions" ADD CONSTRAINT "student_questions_model_id_fk" FOREIGN KEY ("model_id") REFERENCES "public"."models"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "model_visits_user_id_idx" ON "model_visits" USING btree ("user_id");--> statement-breakpoint
CREATE INDEX "model_visits_model_id_idx" ON "model_visits" USING btree ("model_id");--> statement-breakpoint
CREATE INDEX "student_questions_user_id_idx" ON "student_questions" USING btree ("user_id");--> statement-breakpoint
CREATE INDEX "student_questions_asked_at_idx" ON "student_questions" USING btree ("asked_at");