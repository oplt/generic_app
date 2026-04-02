import { useState } from "react";
import dayjs, { type Dayjs } from "dayjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
    Alert,
    Box,
    Button,
    Chip,
    Divider,
    Drawer,
    MenuItem,
    Skeleton,
    Stack,
    TextField,
    Typography,
} from "@mui/material";
import {
    AssignmentTurnedIn as TaskIcon,
    ChevronLeft as ChevronLeftIcon,
    ChevronRight as ChevronRightIcon,
    Event as EventIcon,
    Schedule as AppointmentIcon,
} from "@mui/icons-material";
import { alpha } from "@mui/material/styles";
import { DateCalendar, PickersDay, type PickersDayProps } from "@mui/x-date-pickers";
import type {} from "@mui/x-date-pickers/AdapterDayjs";
import { createCalendarItem, listCalendarItems, type CalendarItem, type CalendarItemType } from "../../api/calendar";
import type { Project, ProjectTaskPriority } from "../../api/projects";
import { useSnackbar } from "../../app/snackbarContext";
import { formatDateOnly, humanizeKey } from "../../utils/formatters";
import { EmptyState } from "../ui/EmptyState";
import { SectionCard } from "../ui/SectionCard";

type DashboardCalendarProps = {
    projects: Project[];
    projectsLoading: boolean;
    onOpenProjects: () => void;
    allowedMonthSpans?: MonthSpan[];
    initialMonthSpan?: MonthSpan;
};

type MonthSpan = 1 | 3 | 6 | 12;

type CalendarDraft = {
    type: CalendarItemType;
    title: string;
    description: string;
    start_time: string;
    end_time: string;
    project_id: string;
    priority: ProjectTaskPriority;
};

const RANGE_OPTIONS: MonthSpan[] = [1, 3, 6, 12];
const ITEM_TYPE_OPTIONS: Array<{ value: CalendarItemType; label: string }> = [
    { value: "event", label: "Event" },
    { value: "appointment", label: "Appointment" },
    { value: "task", label: "Task" },
];
const TASK_PRIORITY_OPTIONS: ProjectTaskPriority[] = ["low", "medium", "high", "urgent"];

function getCalendarColumns(monthSpan: MonthSpan) {
    return {
        xs: "1fr",
        md:
            monthSpan === 1
                ? "1fr"
                : monthSpan === 3
                    ? "repeat(2, minmax(0, 1fr))"
                    : "repeat(2, minmax(0, 1fr))",
        xl:
            monthSpan === 1
                ? "1fr"
                : monthSpan === 3
                    ? "repeat(3, minmax(0, 1fr))"
                    : monthSpan === 6
                        ? "repeat(3, minmax(0, 1fr))"
                        : "repeat(4, minmax(0, 1fr))",
    } as const;
}

function formatTimeValue(value: string) {
    return new Intl.DateTimeFormat(undefined, {
        hour: "numeric",
        minute: "2-digit",
    }).format(new Date(`1970-01-01T${value}`));
}

function formatItemTime(item: CalendarItem) {
    if (!item.start_time) {
        return item.type === "task" ? "Due anytime" : "All day";
    }
    if (!item.end_time) {
        return formatTimeValue(item.start_time);
    }
    return `${formatTimeValue(item.start_time)} to ${formatTimeValue(item.end_time)}`;
}

function getItemIcon(type: CalendarItemType) {
    if (type === "task") {
        return <TaskIcon fontSize="small" />;
    }
    if (type === "appointment") {
        return <AppointmentIcon fontSize="small" />;
    }
    return <EventIcon fontSize="small" />;
}

function buildEmptyDraft(projects: Project[], type: CalendarItemType = "event"): CalendarDraft {
    return {
        type,
        title: "",
        description: "",
        start_time: "",
        end_time: "",
        project_id: projects[0]?.id ?? "",
        priority: "medium",
    };
}

export function DashboardCalendar({
    projects,
    projectsLoading,
    onOpenProjects,
    allowedMonthSpans = RANGE_OPTIONS,
    initialMonthSpan = 3,
}: DashboardCalendarProps) {
    const queryClient = useQueryClient();
    const { showToast } = useSnackbar();
    const [monthSpan, setMonthSpan] = useState<MonthSpan>(initialMonthSpan);
    const [monthOffset, setMonthOffset] = useState(0);
    const [selectedDateKey, setSelectedDateKey] = useState<string | null>(null);
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [draft, setDraft] = useState<CalendarDraft>(buildEmptyDraft(projects));
    const [formError, setFormError] = useState("");

    const today = dayjs().startOf("day");
    const visibleMonthStart = today.startOf("month").add(monthOffset, "month");
    const visibleMonths = Array.from({ length: monthSpan }, (_, index) =>
        visibleMonthStart.add(index, "month")
    );
    const queryStart = visibleMonths[0].startOf("month").startOf("week").format("YYYY-MM-DD");
    const queryEnd = visibleMonths[visibleMonths.length - 1]
        .endOf("month")
        .endOf("week")
        .format("YYYY-MM-DD");
    const selectedDate = selectedDateKey ? dayjs(selectedDateKey) : null;

    const { data: calendarItems, isLoading, error } = useQuery({
        queryKey: ["calendar", "items", queryStart, queryEnd],
        queryFn: () => listCalendarItems(queryStart, queryEnd),
    });

    const itemsByDate = (calendarItems ?? []).reduce<Record<string, CalendarItem[]>>((accumulator, item) => {
        accumulator[item.date] = [...(accumulator[item.date] ?? []), item];
        return accumulator;
    }, {});
    const selectedDateItems = selectedDateKey ? itemsByDate[selectedDateKey] ?? [] : [];
    const daySize = monthSpan >= 6 ? 34 : 40;

    const createItemMutation = useMutation({
        mutationFn: () =>
            createCalendarItem({
                type: draft.type,
                title: draft.title.trim(),
                description: draft.description.trim() || null,
                date: selectedDateKey ?? today.format("YYYY-MM-DD"),
                start_time: draft.type === "task" ? null : draft.start_time || null,
                end_time: draft.type === "task" ? null : draft.end_time || null,
                project_id: draft.type === "task" ? draft.project_id || null : null,
                priority: draft.type === "task" ? draft.priority : null,
            }),
        onSuccess: async (item) => {
            await queryClient.invalidateQueries({ queryKey: ["calendar", "items"] });
            if (item.type === "task") {
                await queryClient.invalidateQueries({ queryKey: ["projects"] });
            }
            setDraft(buildEmptyDraft(projects, draft.type));
            setFormError("");
            showToast({
                message:
                    item.type === "task"
                        ? "Task scheduled on the calendar."
                        : `${humanizeKey(item.type)} saved.`,
                severity: "success",
            });
        },
        onError: (mutationError) => {
            setFormError(
                mutationError instanceof Error ? mutationError.message : "Failed to save calendar item."
            );
        },
    });

    function openDay(value: Dayjs | string) {
        const nextDateKey =
            typeof value === "string" ? value : value.startOf("day").format("YYYY-MM-DD");
        setSelectedDateKey(nextDateKey);
        setDrawerOpen(true);
        setFormError("");
        setDraft((current) => ({
            ...current,
            project_id: current.project_id || projects[0]?.id || "",
        }));
    }

    function submitDraft() {
        if (!selectedDateKey) {
            setFormError("Choose a day before adding a calendar item.");
            return;
        }
        if (draft.title.trim().length < 2) {
            setFormError("Title must be at least 2 characters.");
            return;
        }
        if (draft.type === "task" && !draft.project_id) {
            setFormError("Select a project for this task.");
            return;
        }
        if (draft.type !== "task" && draft.end_time && !draft.start_time) {
            setFormError("Start time is required when end time is set.");
            return;
        }
        if (
            draft.type !== "task" &&
            draft.start_time &&
            draft.end_time &&
            draft.end_time <= draft.start_time
        ) {
            setFormError("End time must be after start time.");
            return;
        }
        createItemMutation.mutate();
    }

    function CalendarDay(props: PickersDayProps) {
        const { day, outsideCurrentMonth, ...other } = props;
        const dateKey = day.format("YYYY-MM-DD");
        const dayItems = itemsByDate[dateKey] ?? [];

        return (
            <Box sx={{ position: "relative" }}>
                <PickersDay
                    {...other}
                    day={day}
                    outsideCurrentMonth={outsideCurrentMonth}
                    disableMargin
                    onClick={(event) => {
                        other.onClick?.(event);
                        openDay(day);
                    }}
                    sx={(theme) => ({
                        width: daySize,
                        height: daySize,
                        fontWeight: 700,
                        borderRadius: "999px",
                        color: outsideCurrentMonth
                            ? theme.palette.text.disabled
                            : theme.palette.text.primary,
                        backgroundColor: "transparent",
                        border: 0,
                        "&.Mui-selected": {
                            backgroundColor: theme.palette.primary.main,
                            color: theme.palette.primary.contrastText,
                        },
                        "&.Mui-selected:hover": {
                            backgroundColor: theme.palette.primary.dark,
                        },
                        "&.MuiPickersDay-today": {
                            border: 0,
                            backgroundColor: alpha(
                                theme.palette.secondary.main,
                                theme.palette.mode === "dark" ? 0.2 : 0.1
                            ),
                        },
                        "&:hover": {
                            backgroundColor: alpha(
                                theme.palette.primary.main,
                                theme.palette.mode === "dark" ? 0.14 : 0.08
                            ),
                        },
                    })}
                />
                {dayItems.length > 0 && (
                    <Stack
                        direction="row"
                        spacing={0.35}
                        justifyContent="center"
                        alignItems="center"
                        sx={{
                            position: "absolute",
                            left: "50%",
                            bottom: -2,
                            transform: "translateX(-50%)",
                            pointerEvents: "none",
                        }}
                    >
                        {dayItems.slice(0, 3).map((item) => (
                            <Box
                                key={item.id}
                                sx={(theme) => ({
                                    width: 5,
                                    height: 5,
                                    borderRadius: "999px",
                                    backgroundColor:
                                        item.type === "task"
                                            ? theme.palette.success.main
                                            : item.type === "appointment"
                                                ? theme.palette.secondary.main
                                                : theme.palette.primary.main,
                                })}
                            />
                        ))}
                    </Stack>
                )}
            </Box>
        );
    }

    return (
        <>
            <SectionCard
                title="Workspace calendar"
                description="Scan the next month, quarter, half-year, or year and add work directly from any day."
                action={
                    <Stack spacing={1} alignItems={{ xs: "stretch", sm: "flex-end" }}>
                        {allowedMonthSpans.length > 1 && (
                            <Stack
                                direction="row"
                                spacing={0.75}
                                flexWrap="wrap"
                                useFlexGap
                                justifyContent="flex-end"
                            >
                                {allowedMonthSpans.map((option) => (
                                    <Button
                                        key={option}
                                        size="small"
                                        variant={monthSpan === option ? "contained" : "outlined"}
                                        onClick={() => setMonthSpan(option)}
                                    >
                                        {option}M
                                    </Button>
                                ))}
                            </Stack>
                        )}
                        <Stack direction="row" spacing={0.75} justifyContent="flex-end">
                            <Button
                                size="small"
                                variant="text"
                                startIcon={<ChevronLeftIcon />}
                                onClick={() => setMonthOffset((current) => current - monthSpan)}
                            >
                                Back
                            </Button>
                            <Button
                                size="small"
                                variant="text"
                                endIcon={<ChevronRightIcon />}
                                onClick={() => setMonthOffset((current) => current + monthSpan)}
                            >
                                Forward
                            </Button>
                        </Stack>
                    </Stack>
                }
            >
                {error && (
                    <Alert severity="error" sx={{ mb: 2 }}>
                        {error instanceof Error ? error.message : "Failed to load calendar items."}
                    </Alert>
                )}

                {isLoading ? (
                    <Box
                        sx={{
                            display: "grid",
                            gap: 1.5,
                            gridTemplateColumns: getCalendarColumns(monthSpan),
                        }}
                    >
                        {visibleMonths.map((month) => (
                            <Skeleton
                                key={month.format("YYYY-MM")}
                                variant="rounded"
                                height={monthSpan >= 6 ? 360 : 420}
                                sx={{ borderRadius: 4 }}
                            />
                        ))}
                    </Box>
                ) : (
                    <Box
                        sx={{
                            display: "grid",
                            gap: 1.5,
                            gridTemplateColumns: getCalendarColumns(monthSpan),
                        }}
                    >
                        {visibleMonths.map((month) => (
                            <Box
                                key={month.format("YYYY-MM")}
                                sx={(theme) => ({
                                    borderRadius: 4,
                                    border: `1px solid ${theme.palette.divider}`,
                                    p: 1.25,
                                    backgroundColor: alpha(
                                        theme.palette.background.paper,
                                        theme.palette.mode === "dark" ? 0.9 : 0.78
                                    ),
                                })}
                            >
                                <DateCalendar
                                    value={selectedDate?.isSame(month, "month") ? selectedDate : null}
                                    onChange={(newValue) => {
                                        if (newValue) {
                                            openDay(newValue);
                                        }
                                    }}
                                    referenceDate={month}
                                    views={["day"]}
                                    showDaysOutsideCurrentMonth
                                    fixedWeekNumber={6}
                                    reduceAnimations
                                    slots={{ day: CalendarDay }}
                                    sx={{
                                        width: "100%",
                                        maxWidth: "none",
                                        m: 0,
                                        "& .MuiPickersCalendarHeader-root": {
                                            px: 1,
                                            mb: 0.5,
                                        },
                                        "& .MuiPickersCalendarHeader-switchViewButton": {
                                            display: "none",
                                        },
                                        "& .MuiPickersArrowSwitcher-root": {
                                            display: "none",
                                        },
                                        "& .MuiPickersCalendarHeader-label": {
                                            fontSize: "1rem",
                                            fontWeight: 700,
                                        },
                                        "& .MuiDayCalendar-header": {
                                            justifyContent: "space-between",
                                            px: 0.75,
                                        },
                                        "& .MuiDayCalendar-weekDayLabel": {
                                            width: daySize,
                                            color: "text.secondary",
                                            fontWeight: 700,
                                        },
                                        "& .MuiDayCalendar-weekContainer": {
                                            justifyContent: "space-between",
                                            mt: 0.5,
                                        },
                                    }}
                                />
                            </Box>
                        ))}
                    </Box>
                )}
            </SectionCard>

            <Drawer
                anchor="right"
                open={drawerOpen}
                onClose={() => setDrawerOpen(false)}
                PaperProps={{
                    sx: {
                        width: { xs: "100%", sm: 420 },
                        p: 2.5,
                    },
                }}
            >
                <Stack spacing={2}>
                    <Box>
                        <Typography variant="h5" sx={{ mb: 0.5 }}>
                            {selectedDateKey ? formatDateOnly(selectedDateKey) : "Select a day"}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                            Add an event, appointment, or a real task due on this day.
                        </Typography>
                    </Box>

                    <Divider />

                    <Box>
                        <Typography variant="subtitle2" sx={{ mb: 1 }}>
                            Day agenda
                        </Typography>
                        {selectedDateItems.length === 0 ? (
                            <EmptyState
                                icon={<EventIcon />}
                                title="Nothing scheduled yet"
                                description="Pick a type below and add the first calendar item for this day."
                            />
                        ) : (
                            <Stack spacing={1}>
                                {selectedDateItems.map((item) => (
                                    <Box
                                        key={item.id}
                                        sx={(theme) => ({
                                            borderRadius: 3,
                                            border: `1px solid ${theme.palette.divider}`,
                                            p: 1.5,
                                            backgroundColor:
                                                item.type === "task"
                                                    ? alpha(
                                                          theme.palette.success.main,
                                                          theme.palette.mode === "dark" ? 0.16 : 0.08
                                                      )
                                                    : theme.palette.background.paper,
                                        })}
                                    >
                                        <Stack spacing={0.75}>
                                            <Stack direction="row" spacing={1} alignItems="center">
                                                {getItemIcon(item.type)}
                                                <Typography variant="subtitle2">{item.title}</Typography>
                                            </Stack>
                                            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                                                <Chip label={humanizeKey(item.type)} size="small" variant="outlined" />
                                                <Chip label={formatItemTime(item)} size="small" variant="outlined" />
                                                {item.project_name && (
                                                    <Chip label={item.project_name} size="small" variant="outlined" />
                                                )}
                                                {item.status && (
                                                    <Chip label={humanizeKey(item.status)} size="small" variant="outlined" />
                                                )}
                                                {item.priority && (
                                                    <Chip
                                                        label={`${humanizeKey(item.priority)} priority`}
                                                        size="small"
                                                        variant="outlined"
                                                    />
                                                )}
                                            </Stack>
                                            {item.description && (
                                                <Typography variant="body2" color="text.secondary">
                                                    {item.description}
                                                </Typography>
                                            )}
                                        </Stack>
                                    </Box>
                                ))}
                            </Stack>
                        )}
                    </Box>

                    <Divider />

                    <Stack spacing={1.5}>
                        <Typography variant="subtitle2">Add new item</Typography>
                        <TextField
                            label="Type"
                            select
                            value={draft.type}
                            onChange={(event) => {
                                const nextType = event.target.value as CalendarItemType;
                                setDraft((current) => ({
                                    ...current,
                                    type: nextType,
                                    start_time: nextType === "task" ? "" : current.start_time,
                                    end_time: nextType === "task" ? "" : current.end_time,
                                    project_id: current.project_id || projects[0]?.id || "",
                                }));
                                setFormError("");
                            }}
                            fullWidth
                        >
                            {ITEM_TYPE_OPTIONS.map((option) => (
                                <MenuItem key={option.value} value={option.value}>
                                    {option.label}
                                </MenuItem>
                            ))}
                        </TextField>
                        <TextField
                            label="Title"
                            value={draft.title}
                            onChange={(event) => {
                                setDraft((current) => ({ ...current, title: event.target.value }));
                                setFormError("");
                            }}
                            fullWidth
                        />
                        <TextField
                            label="Description"
                            value={draft.description}
                            onChange={(event) =>
                                setDraft((current) => ({ ...current, description: event.target.value }))
                            }
                            fullWidth
                            multiline
                            minRows={3}
                        />

                        {draft.type === "task" ? (
                            <>
                                <TextField
                                    label="Project"
                                    select
                                    value={draft.project_id}
                                    onChange={(event) =>
                                        setDraft((current) => ({ ...current, project_id: event.target.value }))
                                    }
                                    fullWidth
                                    disabled={projectsLoading}
                                    helperText={
                                        projects.length > 0
                                            ? "Task will be created in Todo with this date as its due date."
                                            : "Create a project first before scheduling tasks from the calendar."
                                    }
                                >
                                    {projects.map((project) => (
                                        <MenuItem key={project.id} value={project.id}>
                                            {project.name}
                                        </MenuItem>
                                    ))}
                                </TextField>
                                <TextField
                                    label="Priority"
                                    select
                                    value={draft.priority}
                                    onChange={(event) =>
                                        setDraft((current) => ({
                                            ...current,
                                            priority: event.target.value as ProjectTaskPriority,
                                        }))
                                    }
                                    fullWidth
                                >
                                    {TASK_PRIORITY_OPTIONS.map((priority) => (
                                        <MenuItem key={priority} value={priority}>
                                            {humanizeKey(priority)}
                                        </MenuItem>
                                    ))}
                                </TextField>
                                {projects.length === 0 && (
                                    <Button variant="outlined" onClick={onOpenProjects}>
                                        Create a project
                                    </Button>
                                )}
                            </>
                        ) : (
                            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.25}>
                                <TextField
                                    label="Start time"
                                    type="time"
                                    value={draft.start_time}
                                    onChange={(event) =>
                                        setDraft((current) => ({ ...current, start_time: event.target.value }))
                                    }
                                    fullWidth
                                    InputLabelProps={{ shrink: true }}
                                />
                                <TextField
                                    label="End time"
                                    type="time"
                                    value={draft.end_time}
                                    onChange={(event) =>
                                        setDraft((current) => ({ ...current, end_time: event.target.value }))
                                    }
                                    fullWidth
                                    InputLabelProps={{ shrink: true }}
                                />
                            </Stack>
                        )}

                        {formError && <Alert severity="error">{formError}</Alert>}

                        <Stack direction="row" spacing={1}>
                            <Button variant="outlined" onClick={() => setDrawerOpen(false)} fullWidth>
                                Close
                            </Button>
                            <Button
                                variant="contained"
                                onClick={submitDraft}
                                disabled={
                                    createItemMutation.isPending ||
                                    (draft.type === "task" && projects.length === 0)
                                }
                                fullWidth
                            >
                                {createItemMutation.isPending ? "Saving..." : "Save"}
                            </Button>
                        </Stack>
                    </Stack>
                </Stack>
            </Drawer>
        </>
    );
}
