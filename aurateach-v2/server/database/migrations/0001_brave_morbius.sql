CREATE INDEX "classrooms_teacher_id_idx" ON "classrooms" USING btree ("teacher_id");--> statement-breakpoint
CREATE INDEX "enrollments_student_id_idx" ON "enrollments" USING btree ("student_id");--> statement-breakpoint
CREATE INDEX "model_visits_visited_at_idx" ON "model_visits" USING btree ("visited_at");