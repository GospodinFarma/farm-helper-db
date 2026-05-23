export async function onRequest(context) {

    const url = new URL(context.request.url);

    const login = url.searchParams.get("login");
    const password = url.searchParams.get("password");

    const usersUrl = "https://gospodinfarma.github.io/farm-helper-db/users.json";

    const response = await fetch(usersUrl);
    const data = await response.json();

    const user = data.users.find(
        u => u.login === login && u.password === password
    );

    if (!user) {
        return Response.json({
            status: "error",
            message: "user_not_found"
        });
    }

    if (user.banned) {
        return Response.json({
            status: "error",
            message: "banned"
        });
    }

    if (new Date() > new Date(user.expires)) {
        return Response.json({
            status: "error",
            message: "subscription_expired"
        });
    }

    return Response.json({
        status: "success",
        expires_at: user.expires,
        subscription_type: "Default"
    });
}
